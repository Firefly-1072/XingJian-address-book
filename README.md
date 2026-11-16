# 星笺 V1：基础版

第一轮迭代，只实现一套可以运行的基础通讯录。

## 已实现

- 联系人列表
- 新增、编辑、删除联系人
- 姓名、电话、邮箱、公司和备注
- 按姓名、电话、邮箱或公司搜索
- SQLite本地持久化
- 基础输入校验和响应式页面

本版本不包含收藏、多联系方式、Excel导入导出和账户系统，这些功能会在后续迭代加入。

## 运行

```powershell
cd "本文件夹路径"
python -m pip install -r requirements.txt
python app.py
```

浏览器访问：`http://127.0.0.1:5000`

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 建议提交信息

```text
feat: implement basic address book
```
