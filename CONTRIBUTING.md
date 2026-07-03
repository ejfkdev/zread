# 贡献指南

感谢您对 Zread 项目的关注！

## 如何贡献

1. **Fork 仓库** - 点击 GitHub 右上角的 Fork 按钮
2. **克隆代码** - `git clone https://github.com/YOUR_USERNAME/zread.git`
3. **创建分支** - `git checkout -b feature/your-feature-name`
4. **提交更改** - `git commit -m "描述您的更改"`
5. **推送分支** - `git push origin feature/your-feature-name`
6. **创建 Pull Request** - 在 GitHub 上提交 PR

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/valeriikot/zread.git
cd zread

# 创建虚拟环境
python -m venv .venv
source .venv/bin/active  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 本地运行测试
python zread.py --help
```

## 代码规范

- 遵循 PEP 8 风格指南
- 添加适当的文档字符串
- 保持代码简洁清晰

## 报告问题

如果您发现 bug 或有功能建议，请在 [Issues](https://github.com/valeriikot/zread/issues) 页面提交。

## 许可证

通过贡献您的代码，您同意将其授权为 MIT 许可证。
