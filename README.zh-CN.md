<p align="center">
  <a href="https://resumeproof.szw19990924.chatgpt.site/match/new?utm_source=github&amp;utm_medium=referral&amp;utm_campaign=skill_repo_202609">
    <img src="docs/images/hero.png" alt="ResumeProof Match：证据优先的简历匹配与交付工作流" width="100%" />
  </a>
</p>

<p align="center">
  <strong>先判断是否匹配，再证明每句话，审核后才生成。</strong>
</p>

<p align="center">
  <a href="https://github.com/caihhhhhh/resume-proof-match/actions/workflows/ci.yml"><img src="https://github.com/caihhhhhh/resume-proof-match/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://developers.openai.com/codex"><img src="https://img.shields.io/badge/Codex-Agent_Skill-111827?style=flat-square" alt="Codex Skill" /></a>
  <a href="https://docs.anthropic.com/en/docs/claude-code"><img src="https://img.shields.io/badge/Claude_Code-Compatible-D97757?style=flat-square" alt="Claude Code" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-10B981?style=flat-square" alt="License: MIT" /></a>
</p>

<p align="center">
  <a href="https://resumeproof.szw19990924.chatgpt.site/match/new?utm_source=github&amp;utm_medium=referral&amp;utm_campaign=skill_repo_202609"><strong>在线体验 →</strong></a> ·
  <a href="README.md">English</a> ·
  <a href="#安装">安装</a> ·
  <a href="#完整流程">完整流程</a>
</p>

# ResumeProof Match

ResumeProof Match 是一个面向 AI Agent 的端到端 Skill，把“简历与 JD 匹配分析”和“基于证据生成、审核、验收简历”合并成一条工作流。

它连续解决两个问题：

1. 这个岗位值不值得投，判断依据是什么？
2. 如何把已有证据写成针对性简历，同时不编造、不夸大？

很多匹配工具给完分数就结束，很多简历工具在事实尚未确认时就开始生成。ResumeProof Match 用同一条可审计的证据链连接两者。

## 先在网页中试用

不想先安装 Skill，也可以直接使用网页版：

**[打开 ResumeProof Match，匹配简历与 JD →](https://resumeproof.szw19990924.chatgpt.site/match/new?utm_source=github&utm_medium=referral&utm_campaign=skill_repo_202609)**

网页版可以上传或粘贴简历与 JD，审核识别文字，查看每项要求对应的简历证据，采用或修改建议，确认完整文字稿，再导出 HTML、PDF 或 DOCX。如果只想先看效果，可以[直接加载完整示例](https://resumeproof.szw19990924.chatgpt.site/match/new?demo=1&utm_source=github&utm_medium=referral&utm_campaign=skill_repo_202609)，不需要上传文件。

如果想先了解判断逻辑，可以阅读[证据优先的简历与 JD 匹配方法](https://resumeproof.szw19990924.chatgpt.site/guide?utm_source=github&utm_medium=referral&utm_campaign=skill_repo_202609)。

当前仓库是面向 AI Agent 的 Skill 与确定性工作流；互动网站的源码单独维护在 [Web App 仓库](https://github.com/caihhhhhh/resumeproof-match-web)。

## 核心特点

- **逐项解释匹配依据**：每个结论都能回到 JD 原句和具体简历证据。
- **三个分数分开看**：岗位匹配度、证据覆盖率、文档就绪度互不替代。
- **不伪装成 ATS 通过率**：评分只辅助决策，不预测招聘系统行为。
- **优化建议有事实状态**：区分“已有证据”“需要确认”“暂不支持”。
- **完整文字稿强制审核**：未经用户明确批准，不生成 HTML、DOCX 或 PDF。
- **QA 与文件哈希绑定**：文字或输出文件变化后，旧的验收结果自动失效。
- **轻量可移植**：核心仅使用 Python 标准库，不需要账号、数据库、RAG 或向量库。

## 安装

\`\`\`bash
npx skills add caihhhhhh/resume-proof-match -g
\`\`\`

安装后，将简历与完整 JD 一起交给 Agent：

> 使用 $resume-proof-match 对比我的简历和这份 JD，说明每个匹配结论的证据，给出真实可用的优化建议，并在生成文件前先让我审核完整文字稿。

## 完整流程

\`\`\`text
简历 + JD + 补充资料
          ↓
拆解岗位要求与硬门槛
          ↓
建立“事实—来源”证据台账
          ↓
生成可解释的匹配与差距报告
          ↓
用户选择要采用的修改
          ↓
完整文字稿审核与批准
          ↓
生成可编辑源文件和 PDF
          ↓
QA 验收与版本化交付
\`\`\`

辅助脚本负责创建工作区、检查跨文件引用、计算分数、记录文字稿批准、绑定 QA 哈希，并阻止不安全交付。

\`\`\`bash
python scripts/resume_proof_match.py new \
  --company "示例公司" \
  --role "增长分析师" \
  --language zh

python scripts/resume_proof_match.py score Resume_Output/Applications/<目录> --write
python scripts/resume_proof_match.py keywords Resume_Output/Applications/<目录> --resume resume.pdf
python scripts/resume_proof_match.py compare Resume_Output/Applications/<目录甲> Resume_Output/Applications/<目录乙>
python scripts/resume_proof_match.py cover-approve Resume_Output/Applications/<目录>
python scripts/resume_proof_match.py cover-qa Resume_Output/Applications/<目录> --file cover-letter.pdf --text passed --facts passed
python scripts/resume_proof_match.py export Resume_Output/Applications/<目录> --output app.zip
python scripts/resume_proof_match.py interview Resume_Output/Applications/<目录> --output interview-prep.md
python scripts/resume_proof_match.py status Resume_Output/Applications/<目录>
python scripts/resume_proof_match.py outcome Resume_Output/Applications/<目录> --status applied
python scripts/resume_proof_match.py approve Resume_Output/Applications/<目录>
python scripts/resume_proof_match.py inspect resume.pdf --max-pages 2
python scripts/resume_proof_match.py qa Resume_Output/Applications/<目录> \
  --file resume.pdf --text passed --facts passed --pagination passed --visual passed
python scripts/resume_proof_match.py deliver Resume_Output/Applications/<目录> \
  --file resume.pdf --delivery-dir Resume_Output/Delivery
\`\`\`

Agent 负责语义分析与写作，CLI 只处理适合确定性执行的状态、引用、评分、批准和交付规则。PDF 文字检查会在可用时调用可选的 \`pypdf\` 或 \`pdftotext\`。

## 评分逻辑

JD 要求分为“必须满足”“加分项”和“不得出现”。正向要求按重要程度动态加权，必须项权重更高；匹配状态分为已有证据、需要确认和暂不支持。

简历排版与表达质量单独计算，避免“文档做得漂亮”掩盖关键资历缺失。完整规则见 [匹配模型](references/matching.md)。

## 隐私与安全

真实简历、个人资料、填充后的证据台账和申请工作区应保存在仓库之外。提交前可运行：

\`\`\`bash
python scripts/resume_proof_match.py safety .
\`\`\`

该 Skill 不会自行投递岗位、上传文件、发布内容、发送邮件或把文件复制到桌面；这些动作都需要用户单独明确授权。

## 常见问题

### 这是 ATS 评分工具吗？

不是。ResumeProof Match 只检查可验证的客观属性——文字可提取、页数限制、关键词、
结构可读性——并输出三个独立的决策参考信号。它永远不会把分数包装成 ATS 通过率。

### 和免费版 `resume-proof` 有什么区别？

[`resume-proof`](https://github.com/caihhhhhh/resume-proof) 是免费的治理层：
事实溯源、批准门禁、QA 验收。这个 Match 版是完整端到端工作流——JD 要求拆解、
可解释的匹配打分、在线网页 demo——全部在一条可审计的链路上。

### 它会替我写简历吗？

兼容的 AI Agent 负责分析和写作，Skill 负责治理：每句话都绑定提供的证据，
完整文字稿未经你明确批准，排版文件一步都不能往前走。

### 支持中文简历吗？

支持。工作区可指定目标语言（`en` / `zh` / `bilingual`），工作流会按目标语言
自然重写，而不是逐句翻译。关键词检查同样支持中文（基于最长公共短语匹配，
不需要分词器）。

### 我的数据会去哪里？

哪里也不去。CLI 只用 Python 标准库在本地运行——无账号、无数据库、无网络请求。
填充了真实信息的工作区请放在公开仓库之外。

## 本地验证

\`\`\`bash
python -m unittest discover -s tests -v
python scripts/resume_proof_match.py safety .
\`\`\`

项目采用 [MIT License](LICENSE)。
