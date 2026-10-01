# 新设备配置与更新

只在迁移、新设备或相关依赖失效时读本页。现有配置是本机事实，不从另一台机器复制绝对路径。

## R 临时目录和包库

`setup_definition_environment.ps1 -Config $Config`、正式 runner 和环境预检共用 `scripts/r_runtime.py`。配置文件相对路径相对于该配置所在目录。

```json
{
  "schema_version": 1,
  "paths": {
    "formal_root": "D:/project/definitions",
    "process_root": "D:/project/process",
    "r_temp_root": "D:/dbcodebook-runtime/temp",
    "r_library": "D:/dbcodebook-runtime/library"
  },
  "executables": {
    "python": "<本机 Python 可执行文件>",
    "rscript": "<本机 Rscript 可执行文件>"
  }
}
```

以上路径是示例，替换为本机安装和可写目录。`r_temp_root`、`r_library` 可省略：临时目录默认沿用现有目录；Windows 默认目录非 ASCII 时使用 PUBLIC 下按用户区分的 ASCII 子目录。无法建立时直接给出配置缺项。包库默认保留；只有明确设置 `r_library` 才切换到该库，旧库不会自动复制或删除。新库缺包需安装，不会假装迁移成功。

```powershell
./scripts/setup_definition_environment.ps1 -Config $Config -InstallMissing
& $Python -X utf8 scripts/check_definition_environment.py --config $Config --mode local
```

安装仅在显式 `-InstallMissing` 时联网；正式运行不会安装。TEMP/TMP/TMPDIR/R_LIBS_USER 的覆盖仅限本次进程调用，结束或失败后恢复；不设置全局 HOME/R_USER。报告原机故障不证明所有中文路径都失败，测试必须区分模拟环境与真实新设备。

## 无 npm/npx 的浏览器工具

1. 在有工具的机器准备已验证版本的完整 `@playwright/cli` 安装树（包括依赖）与兼容 Node；保留版本及来源。不要只复制一个 cli.js，也不要伪造 npx 包装器。
2. 目标机配置 `executables.node` 为实际 node.exe，`executables.playwright_cli` 为该安装树真实 CLI JavaScript 入口。配置入口优先于 PATH，缺失会直接报错；不会悄悄换工具。
3. 运行 `check_definition_environment.py --config $Config --mode browser --browser chrome`（按既定浏览器替换）。探测成功后才按浏览器会话规则确认控制和登录。

配置的 JS 入口直接由 Node 执行，不需要 npm/npx；未配置时才寻找已安装 CLI 或 npx 离线缓存。预检和生产动作不联网安装包。缺少安装树时须先完成依赖供应；离线预检不会自动取得不存在的软件。

## 仓库改动与安装副本

先检查 Git 状态并保存本地配置和未提交改动，不用 reset/覆盖安装清除现场。修改公共代码后运行 `tests/run_all.ps1 -Config $Config -SkillValidator $Validator`，登记验收矩阵中的实际覆盖和未测边界，再提交可追溯版本。推送、部署按用户授权执行。

安装目录若为 junction/symlink，核实目标即维护仓库，修改已直接生效；独立克隆则在保留本机 config.local.json 后更新到同一提交，再运行本机环境预检。比较 `git rev-parse HEAD`，不要用“文件已复制”替代版本核对。目标机有未提交修改时先合并，不强制覆盖。

## 首次索引和台账

在当前数据库成果根查找 `主题索引.md` 和 `定义验收台账.md`。不存在时各创建一次，不覆盖既有文件；主题编号先核对现有目录和已登记编号。

- 主题索引最小列：编号、主题、正式目录、状态。
- 验收台账最小列：编号、检查日期、结果证据路径、网站地址、用户验收状态。

新行只登记本次实际结果；未同步或未获用户验收保持待处理，不预填完成。
