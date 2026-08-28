# Contributing to DiceFrame

感谢你为 DiceFrame 提交问题、文档、测试、代码或内容贡献。

## 从哪里开始

- 使用前先查阅 [README](README.md) 和 [用户手册](https://github.com/diceframe/diceframe-content/blob/main/docs/zh/guide.md)。
- Bug、需求和架构讨论优先提交到 [GitHub Issues](https://github.com/diceframe/diceframe/issues)。
- 代码或文档改动请发 Pull Request，并在描述中说明动机、行为变化和验证方式。
- 插件和内容包请遵循 [插件开发指南](https://github.com/diceframe/diceframe-content/blob/main/docs/zh/plugin-development.md) 及 [插件审核规则](https://github.com/diceframe/diceframe-content/blob/main/docs/zh/plugin-registry.md)。
- Android 客户端在独立仓库 [diceframe-mobile](https://github.com/diceframe/diceframe-mobile)，其 Bug、需求与代码贡献请提交到该仓库；APK 等发布物见 [Releases](https://github.com/diceframe/diceframe-mobile/releases)。

## 修改原则

- 保持 Web API 字段向后兼容；前端和未来的 Bot 都可能消费这些接口。
- 新功能同时补齐必要的测试、用户手册和迁移说明。
- 复用现有分层、服务和共享 helper，不在核心层引入 WebUI 依赖。
- 不提交运行时存档、个人数据、API Key、构建产物或本机配置。
- 自动化账号（例如 `claude[bot]`、`github-actions[bot]`、`web-flow`）的提交记录保持原样，不通过改作者信息来隐藏或冒充人工贡献。

## 本地验证

前端改动至少运行：

```bash
cd frontend-v2
npm run typecheck
npm run lint
npm test -- --maxWorkers=1
npm run build
```

后端改动请按仓库现有测试配置运行对应的 Python 测试；涉及真实浏览器交互时，再补充 Playwright 验证。

Pull Request 上的 Browser smoke 会保留完整日志，但浏览器或运行环境波动不会单独阻塞贡献；类型检查、单元测试、构建和后端检查仍是合并门槛。合并到 `main` 前会再次严格执行浏览器冒烟。

## 贡献者名单

GitHub 的 [Contributors](https://github.com/diceframe/diceframe/graphs/contributors) 页面自动按提交统计贡献，因此可能包含 CI、发布和代码助手等机器人账号。这是提交归属的准确记录，不等同于人工开发者名单，也不需要手动维护。

如果未来需要一份只列人工贡献者的鸣谢名单，应单独维护 `CONTRIBUTORS.md`，并在获得本人同意后添加；不要修改 Git 历史来处理机器人记录。
