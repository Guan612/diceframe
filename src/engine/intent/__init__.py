"""Intent layer: structured player intents independent of AI output.

Intent 层回答"玩家想做什么"。它只解析玩家自己的行动文本（规则解析 +
轻量匹配，不消耗 LLM），把结果交给经济恢复层与既有 proposal 系统对接：

```text
Player action → PurchaseIntent → evidence repair → pending proposal
```

AI 叙事仍不是交易事实；恢复出的提案保持 pending，付款人确认前不动钱。
"""
