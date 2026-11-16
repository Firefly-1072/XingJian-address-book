# 代码规范

## 通用规范

1. 文件统一使用 UTF-8 编码，结尾保留一个换行符。
2. 变量和函数使用能够表达用途的英文名称，禁止无意义缩写。
3. 每次提交只处理一个明确主题，提交前先运行测试并检查页面。
4. 禁止提交数据库、虚拟环境、账号密码、密钥和编辑器缓存。

## Python

- 遵循 PEP 8，使用4个空格缩进。
- 函数名和变量名使用 `snake_case`，常量使用 `UPPER_CASE`。
- SQL 必须使用参数化查询，不能拼接用户输入。
- API 错误统一返回 `{"error": "中文说明"}` 和合适的 HTTP 状态码。

## HTML、CSS 与 JavaScript

- HTML 使用语义化元素，并为图标按钮提供 `aria-label`。
- CSS 优先使用类选择器；颜色、间距等公共值放在 `:root` 变量中。
- JavaScript 使用 `const`/`let`，禁止使用 `var`。
- 所有用户输入在插入 HTML 前必须转义；网络请求统一通过 `api()` 处理错误。

## Git Commit 格式

```text
类型: 简短说明
```

可用类型：`feat`、`fix`、`test`、`docs`、`style`、`refactor`。

示例：

```text
feat: add contact favorite filter
test: cover Excel import and export
docs: add local setup guide
```
