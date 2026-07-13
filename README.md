# Reverse Editing Workflow

语言 / Language: 中文 | [English](README.en.md)

> Local-first Codex Skill + Claude Code workflow for turning a short-video reference into an editable internal production package.

## 能做什么

`reverse-editing-workflow` 将每条参考视频隔离成独立 `project_id`，并通过小闭环生成和验证：

- 参考 intake、视频分析、镜头结构
- storyboard / HTML previs
- 可编辑 copy、voiceover、subtitle、word timing、audio plan
- WebVTT / SRT 导出
- Tesseract 抽帧 OCR + 人工 contact sheet 复核
- 人工 QC override 审计与本地非发布占位记录
- 按当前视频动态推导的 N-slot 剪映 seed clone
- clone-local 短素材末帧延长
- 文件级、用户报告、截图、录屏四种诚实验收层级

`17-slot` 是一次真实 forward test 和回归样本，不是固定规则；不同视频按自己的 storyboard/previs 决定 N。

## 安装成 Codex Skill

```bash
git clone https://github.com/zkbys/reverse-editing.git
mkdir -p ~/.codex/skills
cp -R reverse-editing/skills/reverse-editing-workflow ~/.codex/skills/
```

重启 Codex 后调用：

```text
Use $reverse-editing-workflow to process this reference as a safe local editable workflow package. Keep download, LibTV, TTS, OCR installation, and Jianying writes disabled until I explicitly authorize the current loop.
```

## Claude Code 入口

Clone 仓库后先读：

```text
CLAUDE.md
skills/reverse-editing-workflow/SKILL.md
```

## 本地 sample

```bash
pip install -r requirements.txt
python3 skills/reverse-editing-workflow/scripts/validate_intake.py \
  --intake samples/fake-corner-noodle/intake.json
python3 skills/reverse-editing-workflow/scripts/init_project.py \
  --intake samples/fake-corner-noodle/intake.json \
  --output-root /tmp/reverse-editing-demo \
  --report /tmp/reverse-editing-demo-init.json
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py \
  --project-dir samples/fake-corner-noodle --force
```

运行完整隔离 smoke（需要本机已有 `ffmpeg/ffprobe`；Tesseract 缺失时会保留 OCR gap，不会自动安装）：

```bash
python3 tests/run_clean_package_smoke.py
```

该 smoke 将 Skill 安装到临时目录，验证 intake、内容层、VTT/SRT、视觉 QC、人工 override、Jianying 默认拒绝写入、17-slot 回归和 5-slot 动态场景。所有草稿和媒体均为临时合成 fixture，不触碰真实剪映目录。

## 默认安全边界

除非用户对当前 loop 明确授权，否则禁止：

- 下载参考视频
- 运行 LibTV / 远程视频生成
- 调用 TTS、付费配音或付费 OCR
- 安装 OCR / FFmpeg 依赖
- 创建、注册或修改剪映草稿
- 烧入字幕或配音
- 上传真实视频、生成视频、剪映草稿、截图、outputs、本机路径、账号信息、密钥或实验过程

任何 OCR、人工 override、文件校验或 GUI 播放通过，都不能把内部预演升级成发布素材。

## 状态

**v1 已冻结（2026-07-11）**。单条视频逆向剪辑工作流已完成端到端闭环：

- intake、镜头分析、storyboard/previs
- 可编辑 content 层（copy/voiceover/subtitle/audio）、VTT/SRT 导出
- Tesseract 抽帧 OCR + 人工 contact sheet 复核
- QC override 审计与本地非发布占位
- 动态 N-slot 剪映 seed clone + 时长适配
- 文件级与 GUI 分层验收
- 确定性内部预览 MP4 渲染
- 结构化交付包（README + KNOWN_LIMITATIONS）

已通过第二条真实参考视频 forward test 和干净包回归（17-slot + 5-slot）。发布仓库只包含通用 Skill、虚构 sample 和合成测试，不包含真实参考资产或项目 outputs。

后续优化全部放入 backlog，不再自动执行。如需继续推进（替换真实素材、真人配音、发布级处理），需显式授权。

当前包已经通过第二条真实参考视频 forward test，并完成干净包的 17-slot 与非 17-slot 回归。发布仓库只包含通用 Skill、虚构 sample 和合成测试，不包含真实参考资产或项目 outputs。

## License

MIT
