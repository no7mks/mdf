# 仓库与当前事实契约

## 固定布局

```text
/
├── .mdf/manifest.yaml
├── AGENTS.md
├── CONTEXT.md
├── CHANGELOG.md
├── docs/
│   ├── research/
│   ├── product/
│   ├── system/
│   └── adr/
├── requirements/
│   ├── req-<ulid>-<slug>.md
│   └── archive/<major.minor>/
├── bugs/
│   ├── bug-<ulid>-<slug>.md
│   └── archive/<major.minor>/
└── changes/
    ├── unreleased/<feature-or-bugfix-slug>/CHANGE.md
    └── <major.minor.patch>/
        ├── CHANGE.md
        └── <feature-or-bugfix-slug>/CHANGE.md
```

`changes/unreleased/`
只保存 feature/bugfix 完成后的待发布快照。hotfix 不创建该阶段；hotfix
closeout 直接生成版本根 `CHANGE.md`。每个稳定版本始终只有一个根 `CHANGE.md`。

## 模板映射

| 模板                                | 用途                             |
| ----------------------------------- | -------------------------------- |
| `manifest.yaml`                     | `.mdf/manifest.yaml` scaffold    |
| `context.md`                        | `CONTEXT.md`                     |
| `agents-managed-block.md`           | `AGENTS.md` MDF marker           |
| `changelog.md`                      | `CHANGELOG.md`                   |
| `docs-*` / `product-*` / `system-*` | 当前事实页面                     |
| `adr.md`                            | `docs/adr/NNNN-slug.md`          |
| `requirement.md`                    | Requirement                      |
| `bug.md`                            | Bug                              |
| `change.md`                         | unreleased feature/bugfix Change |

版本根 Change 由 MDF closeout 直接在目标仓库生成，不要求用户复制模板。

## Manifest

`.mdf/manifest.yaml` 是控制面。`schema_version` 必须为
`2`；`versioning.latest_release` 只能是稳定 SemVer 或 `null`，`unreleased`
不是版本线值。它还包含共享验证配置：

```yaml
verification:
  commands:
    - "python3 -m pytest -q"
```

初始化态可使用空列表；ready、full
validation 与 closeout 要求非空的字符串列表。命令在目标仓库执行，产物必须自行清理或被
`.gitignore` 忽略。

## YAML 子集

Core 用内置解析器（`scripts/mdf_core/yamlutil.py`）解析 manifest 与全部 MDF 文档 frontmatter，
不依赖 PyYAML。只支持以下子集，写法不要超出：

- 空格缩进的映射与 `- ` 列表；缩进含 tab 报 `invalid_yaml`。
- `key:` 后无值表示嵌套映射或列表（由下一行是否为 `- `
  决定），不是 null；要写 null 必须显式写 `null` 或 `~`。
- 标量：`null`/`~` 解析为 null；`true/yes/on` 与
  `false/no/off`（大小写不敏感）解析为布尔；纯整数解析为数字； `{}`
  为空映射；`[a, b]` 为 flow
  list，元素递归按标量解析；单双引号字符串去引号（双引号支持 `\\` 与 `\"`
  转义）；其余内容原样保留为字符串。
- 井号前有空格或 tab 的 `#` 起为行内注释；引号内的 `#` 不算注释。
- 不支持 block
  scalar（`|`、`>`）、多行字符串、锚点与别名；多行内容用列表或多个字段表达。

closeout 按解析后的 `status` 与 `found_in` 判断。因此 `status: "ready" # note`
和 `found_in: 'unreleased' # note`
与裸值语义相同；closeout 写回这些字段时使用规范裸值。

## 当前事实

一个 Git 仓库只对应一个 MDF 当前上下文和一条版本线。产品和系统页面表达当前 checkout 的实际行为，并用代码、配置、schema、
测试或生成物作为 evidence。计划、Requirement、Bug、Iteration 和 Change 不得冒充当前事实；MDF 不管理 PR、RFC、
外部 tracker、owner、priority、Task 或迭代。

## 调研材料

`docs/research/` 保存调研原文、候选方案、对比和尚未确认的结论。它们不是当前
事实页，不填入事实基线，也不要求 fact frontmatter。已确认的决策另建 ADR；实现
后的当前行为另写产品或系统事实页。README 仅作导航，应链接文档入口、调研和 ADR。

## Fact frontmatter：evidence 与 generated

每个当前事实文档至少声明一条 evidence，支持两种形态：

```yaml
# 形态一：逐条 evidence，各自带验证方式
evidence:
  - path: "<repo-relative-path>"
    verification: "<如何验证>"
# 形态二：一组路径共享验证方式
evidence:
  paths: ["<repo-relative-path>"]
  verification: "<如何验证>"
```

evidence 路径必须仓库相对、存在且被 Git 跟踪，并带 verification 方式（裸字符串列表形态缺 verification 会报
finding）；full
audit 下 evidence 在文档之后变更会报 `evidence.stale`。

由脚本生成的文档额外声明 `generated`：

```yaml
generated:
  source: "<repo-relative-source>"
  generator: "<repo-relative-executable>"
```

`source` 必须是仓库内存在且被跟踪的文件；`generator`
必须是仓库内可执行文件。full
audit 校验这些元数据及 Git 陈旧性，但不复制仓库、不运行 generator，也不自动比较生成内容；内容一致性属于语义审计。模板见
`assets/templates/generated-fact.md`。

## Planning 根目录与 move-change

外部 planning 目录只认三个根：`.scratch/`、`.iterations/`、`iterations/`。

- `planning-candidates --branch-slug <slug>`
  在三个根下递归匹配相对路径 slug 相同的目录，报告 `none`/
  `unique`/`ambiguous`。
- `move-change --source <path>`
  的源必须位于某个 planning 根之内、其相对该根的路径 slug 与 `--branch-slug`
  一致，且不含符号链接；源中的保留名 `CHANGE.md`
  必须是合法 Change 文件，否则拒绝。目标是
  `changes/unreleased/<slug>`；目标已存在且来源不同、或源包含目标时拒绝。移动后重写仓库内 Markdown 链接，
但不改写源树内部的 opaque 文件。

## CHANGELOG

根 `CHANGELOG.md` 只列稳定版本，不含 Unreleased 章节。版本目录的根 `CHANGE.md`
是详细 closeout、结果、outcome、found-in 转换、SemVer 和审计记录；CHANGELOG 只做读者索引。
