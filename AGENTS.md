# Codex / AI 协作入口

修改代码前，按任务范围阅读：

1. 架构事实来源：
   - [docs/ARCHITECTURE_CN.md](docs/ARCHITECTURE_CN.md)
   - [docs/ARCHITECTURE_EN.md](docs/ARCHITECTURE_EN.md)
2. 工程修改规则：
   - [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md)
3. 涉及权限、存档、迁移、多人、规则等高风险行为时：
   - [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md) 的 Testing 章节（§15）
4. 涉及已有重大架构决策时：
   - [docs/adr/](docs/adr/)

关键原则：

- 当前架构是事实来源，不是不可改变的路线图。
- 可以做大型重构、拆分、迁移和 breaking change；必须显式处理受影响的 contract。
- 不要把翻译后的 display name 当作 canonical identity。
- Locale 不得无意改变 mechanics。
- compatibility 应留在明确边界，不要散回正常业务逻辑。
- specific ruleset 不应反向污染 generic engine。
- migration correctness > migration completeness；无法证明安全时 fail closed。
- 系统模板不得无条件覆盖用户数据。
- AI 可以改架构，但不能靠猜测创造字段、API 或迁移语义。
