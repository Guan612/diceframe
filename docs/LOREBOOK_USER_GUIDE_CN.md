# Lorebook v2 用户指南

世界书是提供给提示词的资料层：它描述可能相关的设定，不替代 WorldState 的当前事实。

导入流程是“选择文件 → 识别格式 → 预览 → 选择绑定范围 → 确认”。预览中的 warning 和
unsupported 字段不会被静默执行；未知扩展会作为数据保留。SillyTavern 的 timed 效果会提示
其 message-based 语义与 DiceFrame authoritative turn tick 的差异。

普通编辑只需填写名称、内容、关键词和可见范围；匹配、递归、概率、分组和 token budget
在高级设置中调整。玩家视角不会得到隐藏条目的名称、数量或诊断原因。
