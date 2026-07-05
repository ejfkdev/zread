# 贡献指南 / Contributing

感谢您对 Zread 项目的关注！ / Thanks for your interest in Zread!

## 如何贡献 / How to Contribute

1. **Fork 仓库** - 点击 GitHub 右上角的 Fork 按钮
2. **克隆代码** - `git clone https://github.com/YOUR_USERNAME/zread.git`
3. **创建分支** - `git checkout -b feature/your-feature-name`
4. **提交更改** - `git commit -m "描述您的更改"`
5. **推送分支** - `git push origin feature/your-feature-name`
6. **创建 Pull Request** - 在 GitHub 上提交 PR

## 开发环境设置 / Development Setup

推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
# 克隆仓库
git clone https://github.com/valeriikot/zread.git
cd zread

# 安装依赖并运行（uv 自动管理虚拟环境）
uv sync
uv run zread -h
```

或使用传统的 venv + pip：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
zread -h
```

构建 Docker 镜像（共享 MCP 服务）：

```bash
docker build -t zread-mcp .
docker compose up -d   # 需要先配置 .env（见 .env.example）
```

## 项目结构 / Project Layout

- `zread/__init__.py` — 整个 CLI 和 MCP 服务都在这一个文件里，带有 PEP 723 内联脚本元数据（可直接 `uv run zread/__init__.py`）
- `zread/locales/messages.zh.yml` / `messages.en.yml` — 所有面向用户的文案（i18n）
- `Dockerfile` / `docker-compose.yml` / `.env.example` — 公司级共享 MCP 服务部署
- `scripts/` — 发布辅助脚本

## 代码规范 / Conventions

- 遵循 PEP 8 风格指南，保持代码简洁清晰
- **所有面向用户的文本必须走 `tr()` 国际化**：同时更新 `messages.zh.yml` 和 `messages.en.yml`，不要在代码里硬编码文案
- **文档双语同步**：改动 `README.md` 时请同步更新 `README.zh.md`（反之亦然）
- 新增会访问网络的功能时，注意区分 zread.ai 模式和直连模式（`--direct`，数据仅来自 GitHub），两条路径都要能工作或给出明确报错
- 提交前手动验证受影响的命令（如 `uv run zread ls golang/go -p`、`uv run zread mcp` 冒烟测试）

## 报告问题 / Reporting Issues

如果您发现 bug 或有功能建议，请在 [Issues](https://github.com/valeriikot/zread/issues) 页面提交。

## 许可证 / License

通过贡献您的代码，您同意将其授权为 MIT 许可证。
By contributing, you agree to license your code under the MIT license.
