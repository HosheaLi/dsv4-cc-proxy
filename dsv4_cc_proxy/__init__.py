# dsv4-cc-proxy — DeepSeek Anthropic API 兼容性代理
#
# 双向代理修复 DeepSeek V4 Anthropic API 兼容性问题:
#   1. 请求端: 为缺 thinking 块的 tool_use assistant 消息注入空 thinking 块
#   2. 请求端: adaptive 等不支持的 thinking 模式 → disabled + 移除 effort
#   3. 响应端: 剥离意外 thinking/thinking_delta/signature_delta SSE 事件

from dsv4_cc_proxy._version import VERSION
from dsv4_cc_proxy.proxy import create_app

__all__ = ["VERSION", "create_app"]
