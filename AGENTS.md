# Codex 协作入口

架构事实来源：

- [docs/ARCHITECTURE_CN.md](docs/ARCHITECTURE_CN.md)
- [docs/ARCHITECTURE_EN.md](docs/ARCHITECTURE_EN.md)

关键规则：不要把翻译后的显示名称当作 identity；V2 不新增后缀全文复制式本地化；兼容逻辑留在 `src/compat/` 或明确的适配边界；Locale 不得改变 canonical identity 或 mechanics；D&D 专属行为不得修改 generic d20。
