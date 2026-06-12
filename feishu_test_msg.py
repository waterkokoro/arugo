import lark_oapi as lark
import json

client = lark.Client.builder() \
    .app_id('cli_a732393dfbf9d01c') \
    .app_secret('GrTbfPy0iH3vOhOal68JkhNYhMFjNuKj') \
    .build()

content = json.dumps({
    'schema': '2.0',
    'config': {'enable_forward': True},
    'body': {
        'elements': [
            {'tag': 'markdown', 'content': '\n'.join([
                '**🧪 飞书 Markdown 测试消息**',
                '',
                '---',
                '',
                '✅ **连接状态**：正常',
                '📡 **通道模式**：WebSocket 长连接 + REST API 发送',
                '',
                '### 测试项',
                '',
                '| 项目 | 状态 |',
                '|------|------|',
                '| WebSocket 连接 | 🟢 在线 |',
                '| REST API 发送 | 🟢 正常 |',
                '| Markdown 表格 | 🟢 渲染正常 |',
                '',
                '飞书机器人集成完毕，开始对话吧 🎉',
                '',
                '---',
                '发送自 **阿尔戈** · Phase 4 飞书集成验证',
            ]),
                'text_align': 'left'
            }
        ]
    }
})

from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

request = CreateMessageRequest.builder() \
    .receive_id_type('open_id') \
    .request_body(
        CreateMessageRequestBody.builder()
        .receive_id('ou_d66e506d5dce03fa45b3479eb5eb89fa')
        .msg_type('interactive')
        .content(content)
        .build()
    ) \
    .build()

response = client.im.v1.message.create(request)
print(f'Success: {response.success()}')
print(f'Code: {response.code}')
print(f'Msg: {response.msg}')
if response.data:
    print(f'Message ID: {response.data.message_id}')
