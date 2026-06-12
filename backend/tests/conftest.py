"""pytest 配置 - 设置测试环境路径"""

import sys
import os

# 确保 backend/ 在路径中，使 agent.* 导入可用
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
