# 星笺 V3：登录系统版

第三轮迭代在功能增强版上加入账户系统和用户数据隔离，是最终展示版本。

## 本轮新增

- 登录和安全退出
- 首次使用注册账号
- 手机号格式验证
- 本地演示验证码
- 忘记密码和手机号验证码重置
- 密码哈希存储
- 登录会话
- 每位用户只能访问自己的联系人
- 星笺登录界面与完整主题

> 当前验证码为课程演示模式：验证码会显示在页面中，并不会真正发送短信。不要将其宣传为生产级短信验证。

## 运行

```powershell
cd "本文件夹路径"
python -m pip install -r requirements.txt
python app.py
```

浏览器访问：`http://127.0.0.1:5000`

第一次使用时点击“注册账号”，输入符合格式的手机号并获取页面显示的演示验证码。

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 建议提交信息

```text
feat: add authentication and user data isolation
```
