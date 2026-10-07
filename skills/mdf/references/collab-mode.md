# Collab-mode 契约

本页规定 release 的 collab-mode 如何交接、接管与联调，供 start / integrate / next / deliver 读取。

执行联调前读取 `references/common.md` 与 `references/delivery-contract.md`；当前会话已完整读取则复用。

## 责任与范围

collab-mode 由一个接手 Agent 同时操作前后端项目的 release worktree。

- start Agent 在本仓准备 release 分支、owner worktree 与 objectives，完成后交接。
- 接手 Agent 在自己的 workspace 中访问两端，直接调度代码、测试、配置、服务与依赖。
- 本模式不 init、不 poll、不 listen、不 send，不使用 `.integration/` 消息通道。
- 两端各自保留 delivery 身份、objectives、roster、提交与报告，不新增跨仓状态文件或 CLI。
- 本模式只改变联调的操作责任；后续 next / deliver 与 auto-pilot / yolo 沿用原授权和确认规则。

## Start 交接

start Agent 完成本仓步骤 5 后，将以下材料交给用户或接手 Agent。

| 材料 | 内容 |
| --- | --- |
| 交付身份 | 本仓名称、release 版本、完整分支名、owner worktree 绝对路径 |
| 已确认范围 | 本版范围、允许修改的内容、非目标、可验证验收 |
| 进度 | objectives 路径、`needs_design`、`has_dev`、roster 与未勾项 |
| 对端信息 | 已知的前后端对应关系、对端仓库或 worktree 路径；未知项明确标注 |

- 本仓 objectives 工作线写 `collab-mode`，联调正文记录交接信息；integrate 保持 `[ ]`。
- start Agent 不要求访问对端，不替接手 Agent 创建对端分支、启动服务或执行联调。
- 独立 start 交接后结束；deliver 内部委托则返回调用方并说明尚待接手。
- next / deliver 尚未接管两端时，也交接并结束；不得把本仓 start 成功视为联调或交付完成。

## 接管条件

接手 Agent 执行 integrate 前，先核对前后端两份已启动的 release worktree。

- 用户已将两端 worktree 交给本 Agent，且当前 workspace 可读写两端并控制所需进程。
- 分别读取两仓 Agent 指令、MDF 配置与交付材料，沿用各自范围与验证命令。
- 用每端绝对路径核对 Git 根、`release/<semver>`、delivery 身份与 objectives。
  - 每端版本分别采用已确认值，不要求两仓版本相同，不从另一端推断版本。
- 两端工作线均为 `collab-mode`，checklist 均含 integrate；已有改动按各仓入口规则处理。
- 对端尚未 start、路径或权限缺失时，报告缺项并保留现场，等待对应 start Agent 准备。
  - 不自动创建第二套分支或 worktree，不接管未经交付的仓库。
- 对两端的每次文件、Git、测试与进程操作，均指定所属 worktree 的绝对路径。

## 联调执行与收口

接手 Agent 按已确认范围执行两端联调，并负责核实两端的结果。

1. 建立覆盖两端的同一个 Goal，完成判据为两端验收通过、冻结、报告与 integrate 勾选完成。
   - 已有外层 Goal 时复用，内部联调完成只回报结果，不提前置外层 complete。
2. 按 objectives 对齐主导方、场景、数据、依赖与验收计划；已确认内容直接沿用。
3. 在对应 worktree 启动前后端及依赖，执行计划；需要开发时按各端 `needs_design` 与 roster 调度。
   - 需要的 design、开发与 converge 仍由原 intent 执行，不按模式跳过。
4. 在缺陷所属仓库补覆盖、修复、复测与提交；不能现场修复时按该仓 Bug 流程处理。
   - 修复遵循 delivery-contract「补覆盖」；不通过跨仓 `bug-request` 转交。
5. 执行真实前后端联调，核实两端验收与整条调用链；分别保存测试报告。
   - 单端测试通过不能代替双端验收；失败继续修复，不勾 integrate。
6. 两端验收通过后，由接手 Agent 核实两端均无更多代码修改，记录冻结结论并提交。
7. 向用户交付两端测试报告与结论；将两仓 objectives 的 integrate 自勾为 `[x]` 并分别提交。
   - 仅两端都完成后，才完成本 intent 自建的 Goal；已有勾选与提交不重复执行。
8. 独立 integrate 报告收口结果；内部委托返回调用方，按既有 next / deliver 继续剩余阶段。

- 从执行联调起强制 Goal。Goal 完成前，用户没让你停，永远不许停下来。
- code-review 仍须等待双端验收、冻结与 integrate 勾选，各仓使用自己的审查基线。
- 每仓随后执行 verify branch → fact audit → close-out；独立 integrate 不自行执行 finish。
