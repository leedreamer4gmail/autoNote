 # 这是一个笔记系统的开发文档

# 工作：做一个笔记经验系统，让别的软件和ai自动记录下他们的经验，并且能够自动查询这些经验来解决问题

# 业务描述

## 业务和角色
1. 前台：负责接受用户发来乱七八糟的信息，登记用户名，然后把这些信息交给lucy
1. lucy：一个秘书，(她连接llm拥有智能)，把收到信息整理成有条理的md文档（她也要阅读autonotehb.md），使用notetools把文档
2. notetools：操作笔记的工具箱，没有智能，里面有很多基础工具，以后还可拓展
    - 写：包括新建new，更新update，删除del，失效unable
    - 读：read
    - 写说明书：把自己的用法和可能踩的坑写入说明书，更新说明书autonotehb.md
3. notedb.db：存储笔记的数据库
    - id：笔记id，唯一标识，自动生成
    - user：笔记所属用户，不能空
    - folder：笔记所属文件夹，方便分类查询，可以空
    - content：笔记内容，md格式，不能空
    - tag：笔记标签，方便分类查询，最多5个，可以空
    - enable：笔记是否有效，T或者F
4. autonotehb.md：笔记说明书，记录怎么使用notetools的接口和注意踩坑的地方，放在服务器，可以在前台直接连接获取
5. 别的ai或者软件得到说明书，可以直接调用notetools来写笔记和读笔记，但是没有lucy给他分类整理了，别的ai必须自己整理好了像lucy一样的md文档才能调用notetools来写笔记
6. transNote.py：可以跟其他笔记互通，并且维护transNotehb.md
7. manual.html：人工上传的页面，有的ai无法调用外来接口，可以根据说明书的格式生成一个json文件在这里上传

# 环境说明
- 运行在linux ubuntu，目前内存8g
- 所有需要依赖的自行安装
- 拥有flaks环境，nginx环境，sqlite环境
- lucy用的LLM
    key:sk-1685481edf7f4d6e89d49a25973e6e94
    base_url (OpenAI):https://api.deepseek.com/ 
    model：DeepSeek-V4-Flash

# 文件说明


# 模块功能


# 使用流程


# 项目路由配置
## nginx
- 目前情况
    - 服务器ip：8.219.6.216
    - 域名：leedreamer.cn
- leedreamer.cn/autonote/gethb 直接获取说明书
- leedreamer.cn/autonote/notetools 直接访问notetools接口