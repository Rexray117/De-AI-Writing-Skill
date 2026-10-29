# De-AI Writing · 中文写作去 AI 味总控

[![DSH Skill](https://img.shields.io/badge/DeepSeek%20Harness-skill-4a7dff)](https://github.com/Rexray117/De-AI-Writing-Skill)
[![version](https://img.shields.io/badge/version-3.0.1-brightgreen)](https://github.com/Rexray117/De-AI-Writing-Skill/releases)
[![license](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)

> 一个 **DeepSeek Harness（DSH）/ Agent Skill**：`de-ai-writing` v3.0.1。

中文写作去 AI 味总控。两大功能：①修改已有文章——先定文体，再把 AI 生成感量化为客观指标（词表密度、句式重复率、模板腔密度、结构指纹），逐处核对后给改写方案，附完整性守卫；②从零生成文案——先逐步与用户确认文体、文风、受众、篇幅等全部要素，严禁擅自推测补料，确认完才动笔。判定标准分层：主矛盾（结论先行、防御性写作、伪排比、细节不服务上下文）优先于次要矛盾（词表句式）。覆盖七大类中文文体（实用说明、专业论证、商务事务、营销转化、叙事创作、社交表达、法规制度）四十余个子类。触发词：去 AI 味、降 AI 率、AI 感、太像 AI 写的、人机味、不像人话、润色、改写、humanize、论文降AI率、公众号文案、帮我写、写文案、通知公告、小红书。不用于规避 AI 检测、瞒过审查或代署名。

## 适用场景

把本仓库整体放进 agent 的技能目录即可按描述自动触发；也可以在对话里直接点名 `de-ai-writing`。

## 目录结构

```
`SKILL.md`
`LICENSE`
`.gitignore`
references/
scripts/
```

## 安装

### DSH（DeepSeek Harness）

技能目录放到用户级技能根：

```powershell
# Windows
git clone https://github.com/Rexray117/De-AI-Writing-Skill.git "$env:USERPROFILE\.dsh\skills\de-ai-writing"
```

```bash
# macOS / Linux
git clone https://github.com/Rexray117/De-AI-Writing-Skill.git ~/.dsh/skills/de-ai-writing
```

也可以用 DSH 的插件管理安装本地目录：

```
plugin_manager action=install_bundle target=<本仓库绝对路径>
```

### 其他 agent（Codex / WorkBuddy / Claude Code）

技能根分别位于 `~/.codex/skills`、`~/.workbuddy/skills`、`~/.claude/skills`，把本仓库克隆成其中的 `de-ai-writing` 子目录即可（技能名以 `SKILL.md` 的 `name: de-ai-writing` 为准）。

## 版本

- 当前版本：**v3.0.1**（与 `SKILL.md` 的 `version` 字段一致）
- 变更记录见仓库提交历史

## License

MIT © 2026 Rexray117
