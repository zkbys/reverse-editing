# Reverse Editing Workflow

语言 / Language: 中文 | [English](README.en.md)

> Alpha preview. This repository packages a local-first reverse-editing workflow as a Codex Skill plus Claude Code instructions.

## 这个项目是什么

`reverse-editing-workflow` 用来把一个短视频参考拆成可复用的工作流包：

- intake 合同
- 独立 `project_id`
- 镜头结构 / storyboard / previs 计划
- 可编辑文案、配音稿、字幕轨、词级时间、音频计划
- 可导入剪映前的 manifest 规划
- 脏字幕 / 画面文字质检边界
- 本地 validation 报告

当前版本重点是工作流骨架和可编辑控制层。默认不下载视频、不跑远程生成、不调用 TTS、不修改剪映草稿。

## 仓库结构

```text
skills/reverse-editing-workflow/   Codex Skill
samples/fake-corner-noodle/        完全虚构 sample project
CLAUDE.md                          Claude Code 使用入口
README.en.md                       English README
requirements.txt                   Python validation dependency
```

## 安装成 Codex Skill

```bash
git clone https://github.com/zkbys/reverse-editing.git
mkdir -p ~/.codex/skills
cp -R reverse-editing/skills/reverse-editing-workflow ~/.codex/skills/
```

重启 Codex 后，可以这样使用：

```text
Use $reverse-editing-workflow to process this reference video as a safe local workflow package: <video link or local file>
```

## Claude Code 使用方式

Clone 仓库后，让 Claude Code 先读：

```text
CLAUDE.md
skills/reverse-editing-workflow/SKILL.md
```

然后给它一个任务：

```text
Use the reverse-editing workflow to process this reference video URL. Keep download disabled until I explicitly authorize it.
```

## 本地体验 sample

安装依赖：

```bash
pip install -r requirements.txt
```

校验 intake：

```bash
python3 skills/reverse-editing-workflow/scripts/validate_intake.py \
  --intake samples/fake-corner-noodle/intake.json
```

dry-run 初始化：

```bash
python3 skills/reverse-editing-workflow/scripts/init_project.py \
  --intake samples/fake-corner-noodle/intake.json \
  --output-root /tmp/reverse-editing-demo \
  --report /tmp/reverse-editing-demo-init.json
```

当项目内已有授权本地视频时，可以运行本地分析（需要系统已有 `ffmpeg/ffprobe`）：

```bash
python3 skills/reverse-editing-workflow/scripts/analyze_reference_video.py \
  --project-dir outputs/<project_id> \
  --force
```

校验内容层并导出 VTT/SRT：

```bash
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py \
  --project-dir samples/fake-corner-noodle
```

当某个项目已经有 `analysis/shot_index.reviewed.json`、`storyboard/storyboard.json` 和 `previs/previs_plan.json` 后，可以生成本地低保真预演页：

```bash
python3 skills/reverse-editing-workflow/scripts/render_previs_html.py \
  --project-dir outputs/<project_id> \
  --force
```

## 默认安全边界

除非你明确授权，否则 workflow 不应该：

- 下载参考视频
- 运行 LibTV 或其他远程视频生成
- 调用 TTS / 配音服务
- 安装 OCR
- 修改剪映草稿
- 把画面里的脏字幕当正式字幕
- 把参考视频原文复制成最终文案

## 当前状态

这是 `alpha` 版本。它适合体验 intake、project setup、schema validation、可编辑内容层、静态 HTML previs 和 sample 项目结构。

尚未完成：

- 真实视频链接到 storyboard/previs 的完整自动链路
- 第二个真实参考视频 forward test
- 真实 LibTV/TTS/OCR/Jianying 修改执行路径

## License

MIT
