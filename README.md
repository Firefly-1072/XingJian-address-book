# 星笺 V2：功能增强版

第二轮迭代在基础通讯录上完成作业规定的核心功能，不包含账户系统。

## 本轮新增

- 收藏/取消收藏联系人
- 收藏联系人快速筛选
- 一个联系人保存多条电话、邮箱、社交账号、地址及其他联系方式
- 按姓名、公司或联系方式搜索
- Excel导出
- 按兼容模板导入Excel
- 导入格式验证、跳过无效记录和结果提示

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
feat: add favorites multiple contact methods and Excel support
```
