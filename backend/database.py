import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "agent.db")


async def get_db():
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """初始化数据库表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 设置表（key-value 存储）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 消息表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Agent 角色模板表 ──
        await db.execute("""
            CREATE TABLE IF NOT EXISTS agent_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                system_prompt TEXT NOT NULL,
                tools TEXT DEFAULT '[]',
                is_builtin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 插入默认配置
        defaults = {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-3.5-turbo",
            "system_prompt": "You are a helpful assistant.",
            "context_window_size": "500",
            "workspace_dir": "",
            "allowed_commands": "ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest,git init,git remote,git branch,git push,curl",
            # 联网搜索默认配置
            "search_provider": "auto",
            "search_api_keys": "{}",
            # 飞书机器人默认配置
            "feishu_config": '{"enabled": false, "app_id": "", "app_secret": "", "verification_token": "", "event_types": ["im.message.receive_v1"]}',
            # ── Agent 定量参数（Phase 5B）──
            "agent_max_iterations": "200",
            "agent_temperature": "0.7",
            "agent_deep_thinking_default": "false",
            "agent_web_search_default": "true",
            "context_auto_summarize_threshold": "0.8",
            "snapshot_max_count": "20",
            "feishu_text_chunk_size": "1800",
            "feishu_queue_maxsize": "100",
            "quality_gate_auto_snapshot": "true",
        }

        for key, value in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        # 种子数据：7 个内置角色模板
        import json as _json
        _builtin_templates = [
            ("finance_agent", "财务专家", "财务分析、预算编制、成本核算、税务筹划",
             """你是一名专业的财务 Agent，负责财务分析、预算编制、成本核算等任务。

核心能力：
1. 财务报表分析（利润表、资产负债表、现金流量表）
2. 预算编制与执行跟踪
3. 成本核算与利润分析
4. 税务筹划建议
5. 现金流预测

工作规则：
- 使用 read_file 读取财务数据文件
- 使用 write_file 输出分析报告
- 使用 run_command 执行计算脚本
- 使用 web_search 查询最新财税政策
- 所有金额精确到两位小数
- 遇到不确定的税务问题，明确标注"仅供参考，请咨询专业税务师"
- 报告使用 Markdown 格式，含表格和关键指标""",
             _json.dumps(["read_file","write_file","edit_file","list_directory","run_command","web_search","remember","recall_memory"])),
            ("code_engineer", "软件工程师", "全栈开发、架构设计、代码实现、技术选型",
             """你是一名全栈软件工程师 Agent，负责代码开发、架构设计和技术实现。

核心能力：
1. 全栈开发（Python/FastAPI + Vue3/TypeScript）
2. 系统架构设计与评审
3. 代码实现与重构
4. 技术方案编写
5. 依赖管理与环境配置

工作规则：
- 使用全部文件操作和命令执行工具
- 修改代码前先 read_file 理解上下文
- 重大改动使用 create_snapshot 创建快照
- 提交代码使用 git_commit_evolution
- 代码风格遵循 PEP 8 (Python) / ESLint (TS)
- 不确定的技术决策列出 pros/cons""",
             _json.dumps([])),
            ("code_reviewer", "代码审查员", "代码审查、质量检查、安全审计、最佳实践建议",
             """你是一名代码审查 Agent，负责审查代码质量、安全性和最佳实践。

核心能力：
1. 代码质量审查（可读性、可维护性、性能）
2. 安全漏洞检测（注入、XSS、敏感信息泄露）
3. 最佳实践检查
4. 测试覆盖率评估

工作规则：
- 使用 read_file 读取待审查代码
- 使用 run_command 运行 linter 和测试
- 审查结果分三级：🔴 阻断 / 🟡 建议 / 🟢 通过
- 每个问题给出具体代码位置和修改建议
- 不直接修改代码，只输出审查报告""",
             _json.dumps(["read_file","list_directory","run_command","web_search"])),
            ("test_writer", "测试工程师", "测试用例生成、自动化测试、覆盖率提升",
             """你是一名测试工程师 Agent，负责编写测试用例和自动化测试。

核心能力：
1. 单元测试（pytest）
2. 集成测试
3. 测试覆盖率分析
4. 边界条件与异常路径测试

工作规则：
- 使用 read_file 理解被测代码
- 使用 write_file 创建测试文件
- 使用 run_command 执行 pytest
- 测试覆盖正常路径、边界条件、异常路径
- 测试文件命名：test_{module_name}.py
- 使用 run_self_tests 运行现有测试套件""",
             _json.dumps(["read_file","write_file","edit_file","list_directory","run_command","run_self_tests"])),
            ("researcher", "研究员", "信息检索、技术调研、竞品分析、文档整理",
             """你是一名研究员 Agent，负责信息检索、技术调研和知识整理。

核心能力：
1. 多源信息检索（web_search）
2. 技术趋势分析
3. 竞品对比研究
4. 调研报告撰写

工作规则：
- 使用 web_search 进行多轮关键词搜索
- 交叉验证信息来源
- 使用 write_file 输出结构化调研报告（Markdown）
- 标注信息来源和时间
- 区分"事实"与"观点" """,
             _json.dumps(["read_file","write_file","web_search","remember","recall_memory"])),
            ("devops_engineer", "运维工程师", "部署管理、环境配置、服务监控、日志分析",
             """你是一名 DevOps 运维 Agent，负责部署管理和服务运维。

核心能力：
1. 服务部署与配置管理
2. 系统监控与告警
3. 日志分析与故障排查
4. 性能优化建议

工作规则：
- 使用 run_command 执行运维操作（需在白名单内）
- 使用 read_file 检查配置文件和日志
- 使用 health_check / run_self_diagnostics 检查服务状态
- 操作前评估风险，高风险操作先 create_snapshot
- 不要在生产环境直接执行危险命令""",
             _json.dumps(["read_file","write_file","edit_file","list_directory","run_command","health_check","run_self_diagnostics","create_snapshot"])),
            ("product_manager", "产品经理", "需求分析、功能规划、用户故事、优先级排序",
             """你是一名产品经理 Agent，负责需求分析和功能规划。

核心能力：
1. 需求分析与拆解
2. 用户故事编写
3. 功能优先级排序（RICE/MoSCoW）
4. PRD 文档撰写

工作规则：
- 使用 write_file 输出 PRD 文档（Markdown）
- 使用 create_goal / add_milestone 创建开发目标
- 每个功能需求附带验收标准
- 优先级使用 P0/P1/P2/P3 标记
- P0=阻断上线, P1=核心体验, P2=提升体验, P3=锦上添花""",
             _json.dumps(["read_file","write_file","web_search","create_goal","add_milestone","list_goals","remember","recall_memory"])),
        ]
        for tid, name, desc, prompt, tools in _builtin_templates:
            await db.execute(
                "INSERT OR IGNORE INTO agent_templates (id, name, description, system_prompt, tools, is_builtin) VALUES (?, ?, ?, ?, ?, 1)",
                (tid, name, desc, prompt, tools)
            )

        await db.commit()
