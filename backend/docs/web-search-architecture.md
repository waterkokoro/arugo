# KUI 联网搜索逻辑设计文档

> 本文档描述 KUI 项目中联网搜索的完整架构设计，方便在其他项目中复刻。

---

## 1. 整体架构

```
用户发起对话
    ↓
Agent（LLM）判断是否需要搜索
    ↓ 调用 web_search tool
搜索入口层（index.ts）
    ↓ 读取配置
自动降级链（autoSearch.ts）
    ↓ 按优先级依次尝试
Provider 层（providers.ts）
  Tavily → Serper → Brave → AnySearch Free（兜底）
    ↓
统一结果格式 SearchResult[]
    ↓
格式化后喂回 LLM 上下文
    ↓
UI 展示参考来源（可折叠列表）
```

**核心文件：**

| 文件 | 职责 |
|------|------|
| `providers.ts` | 各搜索服务商的 API 调用 + 统一输出格式 |
| `autoSearch.ts` | 自动降级链逻辑，单 Provider / Auto 模式切换 |
| `index.ts` | 对外暴露的搜索入口，读取用户配置 |
| `tools.ts` | 将 `web_search` 注册为 Agent 工具（function calling） |
| `SearchTab.tsx` | 设置面板 UI，配置搜索服务商和 API Key |

---

## 2. 数据模型

### 2.1 统一搜索结果

所有 Provider 都返回同一格式，屏蔽各 API 的差异：

```typescript
interface SearchResult {
  title: string;   // 网页标题
  url: string;     // 原始链接
  content: string; // 摘要/正文片段
}
```

### 2.2 搜索配置（持久化到数据库）

```typescript
// settings 表中存储的两个字段
search_provider: "auto" | "tavily" | "serper" | "brave" | "anysearch_free"
search_api_keys: Record<string, string>  // { tavily: "tvly-xxx", serper: "xxx", brave: "xxx" }
```

### 2.3 搜索响应载体

```typescript
interface SearchPayload {
  query: string;
  results: SearchResult[];
  provider: string;           // 实际使用的 provider 名
  diagnostics: {
    attempts: SearchAttempt[] // 每次尝试的诊断记录
  };
}

interface SearchAttempt {
  provider: string;
  status: "ok" | "empty" | "error";
  resultCount?: number;
  error?: string;
}
```

---

## 3. Provider 层实现（providers.ts）

每个 Provider 是一个独立函数，接收 `(query, maxResults, apiKey)` 返回 `SearchResult[]`。

### 3.1 支持的 Provider

| Provider | API 端点 | 认证方式 | 免费额度 | 特点 |
|----------|----------|----------|----------|------|
| **Tavily** | `POST https://api.tavily.com/search` | `Authorization: Bearer {key}` | 1000次/月 | AI 原生搜索，返回干净结构化内容，英文覆盖优 |
| **Serper** | `POST https://google.serper.dev/search` | `X-API-KEY: {key}` | 注册送2500次 | Google 搜索结果，中文覆盖最好 |
| **Brave** | `GET https://api.search.brave.com/res/v1/web/search?q=...` | `X-Subscription-Token: {key}` | 2000次/月 | 独立索引，隐私友好 |
| **AnySearch Free** | `POST https://api.anysearch.com/v1/search` | 无需认证 | 无限 | 匿名免费，作为兜底方案 |

### 3.2 关键设计点

**统一超时：** 所有请求设置 30 秒超时 `AbortSignal.timeout(30_000)`

**速率限制错误：** 自定义 `SearchRateLimitError` 类，当收到 `429` 或 `402` 时抛出，用于降级逻辑区分

```typescript
if (res.status === 429 || res.status === 402) {
  throw new SearchRateLimitError(`Tavily API ${res.status}`);
}
```

**结果字段映射：** 每个 API 的返回字段不同，统一映射到 `{title, url, content}`

```
Tavily:  r.title, r.url, r.content
Serper:  r.title, r.link→url, r.snippet→content
Brave:   r.title, r.url, r.description→content
AnySearch: r.title, r.url, r.content|r.description|r.snippet
```

---

## 4. 自动降级链（autoSearch.ts）

这是整个搜索系统的核心策略。

### 4.1 Auto 模式（推荐）

```
用户选择 "auto"
    ↓
过滤出已配置 API Key 的 Provider
    ↓
构建降级链：[有Key的Provider...] + [anysearch_free]
    ↓
依次尝试，第一个返回非空结果的成功
    ↓
全部失败则返回空结果
```

伪代码：

```typescript
const configuredApis = API_PROVIDERS.filter(p => !!apiKeys[p]);
const chain = [...configuredApis, "anysearch_free"];

for (const provider of chain) {
  try {
    const results = await runProvider(provider, query, ...);
    if (results.length > 0) return { results, provider }; // 成功
    // 空结果，继续尝试下一个
  } catch (err) {
    // 记录错误，继续尝试下一个（包括 rate limit）
    continue;
  }
}
return { results: [], provider: "none" };
```

### 4.2 单 Provider 模式

```
用户指定某个 Provider
    ↓
如果没有配置 API Key → 自动降级到 Auto 模式
    ↓
调用指定 Provider
    ↓
如果失败 → 尝试 AnySearch Free 作为兜底
    ↓
全部失败则返回空结果
```

### 4.3 API Key 验证

```typescript
export async function verifySearchKey(provider, apiKey): Promise<boolean> {
  if (provider === "anysearch_free") return true;
  try {
    await runProvider(provider, "test", 1, { [provider]: apiKey }, "en");
    return true;
  } catch {
    return false;
  }
}
```

---

## 5. Agent 工具集成（tools.ts）

搜索被注册为 LLM 的 function calling 工具 `web_search`：

```typescript
web_search: tool({
  description: "Search the web for real-time information. Use when you need the latest news, technical docs, current events, or any external knowledge not in your training data.",
  parameters: z.object({
    query: z.string().describe("search keywords"),
    maxResults: z.number().optional().describe("max results, default 10"),
  }),
  execute: async ({ query, maxResults }) => {
    const payload = await webSearch(query, { maxResults: maxResults ?? 10 });
    // 格式化为编号列表喂给 AI
    const formatted = payload.results
      .slice(0, 10)
      .map((r, i) => `${i + 1}. **${r.title}**\n${r.url}\n${r.content}`)
      .join("\n\n");
    return { query, provider: payload.provider, results: payload.results, formatted };
  },
})
```

**关键：** `webSearchEnabled` 参数控制是否注入该工具，用户可在 UI 中开关联网搜索。

---

## 6. UI 层

### 6.1 设置面板（SearchTab.tsx）

- Radio 组选择搜索服务商（auto / tavily / serper / brave / anysearch_free）
- 根据选择动态显示需要配置的 API Key 输入框
- Auto 模式下显示所有 API Provider 的 Key 输入框
- 每个 Key 旁有「验证」按钮，调用 `verifySearchKey` 做测试请求

### 6.2 对话中的搜索反馈

- **搜索中状态：** 脉冲动画指示器（CSS `@keyframes pulse`）
- **参考来源：** 可折叠的 `<details>` 列表，展示搜索结果标题和链接

```css
.kui-search-indicator {
  animation: kui-pulse 1.5s ease-in-out infinite;
}
@keyframes kui-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

---

## 7. 复刻指南

在其他项目中复刻此搜索系统，按以下步骤：

### Step 1：复制 Provider 层

```
providers.ts → 原样复制，只需 SearchResult 接口和各 search 函数
```

### Step 2：复制降级链

```
autoSearch.ts → 原样复制 SearchConfig / SearchPayload / autoSearch 函数
```

### Step 3：适配配置存储

KUI 用 SQLite 存 settings 表，你需要替换为项目自身的配置方案：
- Electron：`electron-store` 或配置文件
- Web：`localStorage` / 后端数据库
- CLI：配置文件 `~/.config/xxx/config.json`

核心只需持久化两个字段：
```json
{
  "search_provider": "auto",
  "search_api_keys": { "tavily": "tvly-xxx", "serper": "xxx" }
}
```

### Step 4：接入你的 Agent / LLM

将 `webSearch()` 注册为工具即可。如果用的是 Vercel AI SDK：

```typescript
import { tool } from "ai";
import { z } from "zod";

const webSearchTool = tool({
  description: "搜索互联网获取实时信息",
  parameters: z.object({ query: z.string() }),
  execute: async ({ query }) => {
    const payload = await webSearch(query);
    return payload.results;
  },
});
```

如果用的是 OpenAI/Anthropic 原生 SDK，将 `web_search` 加入 tools 列表并在 tool_calls 循环中处理即可。

### Step 5（可选）：添加 UI

- 设置页：Radio 选择 Provider + Input.Password 填 API Key + 验证按钮
- 对话页：搜索中显示 loading，搜索后展示参考来源列表

---

## 8. 服务商申请链接

| Provider | 申请地址 | 备注 |
|----------|----------|------|
| Tavily | https://tavily.com | 注册即送 1000 次/月 |
| Serper | https://serper.dev | 注册送 2500 次 |
| Brave | https://brave.com/search/api/ | 免费 2000 次/月 |
| AnySearch | 无需申请 | 匿名免费，无需配置 |

---

## 9. 设计总结

| 设计决策 | 理由 |
|----------|------|
| 统一 `SearchResult` 接口 | 屏蔽各 API 字段差异，上层代码不关心具体 Provider |
| Auto 模式 + 降级链 | 用户只需配一个 Key 即可享受高可用，全部挂了还有免费兜底 |
| 30s 超时 + `SearchRateLimitError` | 避免搜索卡死，rate limit 时自动跳到下一个 Provider |
| AnySearch Free 兜底 | 零配置即可使用，降低新用户门槛 |
| 搜索结果限制 10 条 | 控制 token 消耗，避免搜索结果太长占满上下文窗口 |
| 格式化为编号列表 | AI 容易理解，也方便 UI 渲染参考来源 |
| `diagnostics.attempts` | 调试时可看到完整的降级路径和每次尝试的结果 |
