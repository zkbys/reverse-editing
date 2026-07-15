# Reverse Editing Workflow

> 把你的对标视频，变成一套可执行、可修改、可复拍的视频制作方案。

---

## 一句话说清楚

上传一条你觉得拍得好的短视频，AI 帮你拆解它的镜头结构、文案节奏和信任逻辑，输出一套完整的制作方案——包括拍摄清单、故事板、可编辑字幕/配音脚本，以及一个剪映可打开的预演工程。

---

## 解决了什么问题

每次想拍视频，最头疼的不是剪辑，而是：

- 不知道拍什么镜头
- 不知道文案怎么写
- 不知道镜头之间怎么衔接
- 拍完后发现和想要的节奏完全不一样

**Reverse Editing Workflow** 的解决方式是：**先找到一条对标视频，逆向拆解它的成功结构，再用这个结构指导你的拍摄和剪辑。**

不是从零创作，而是有结构地复刻和优化。

---

## 完整流程：输入 → 处理 → 输出

```
【输入】                          【处理】                          【输出】
一条参考视频        →    ① AI 分析镜头结构        →    镜头拆解报告
                        （需视频理解 AI Agent）         + 参考帧 contact sheet

门店/产品基础信息    →    ② 生成故事板 + 拍摄指导     →    HTML 预演页面
（名称、城市、产品等）      （需 AI 文案能力）              + 拍摄清单

                        ③ 生成可编辑内容层          →    文案脚本
                           （配音脚本、字幕时间轴、      + 配音脚本
                            词级时间戳）                + VTT/SRT 字幕文件
                                                       + 音频混合计划

                        ④ 视频素材 QC              →    OCR 抽帧复核报告
                           （Tesseract 本地 OCR）       + 人工 contact sheet

                        ⑤ 剪映工程组装             →    可打开的剪映草稿
                           （本地脚本操作剪映）          + 完整时间线
                                                       + 可替换的 N 个视频 slot

                        ⑥ 确定性渲染预览           →    内部预览 MP4
                           （FFmpeg 本地渲染）          + 交付包
```

---

## 基础版 vs 完整版

### ✅ 基础版（开箱即用）

不需要任何 API，本机安装即可使用：

| 能力 | 需要 |
|------|------|
| 镜头结构分析 | FFmpeg + ffprobe（本机） |
| 故事板与预演 | 具备视频理解能力的 AI Agent |
| 可编辑文案/配音/字幕层 | AI Agent |
| 字幕 VTT/SRT 导出 | Python + jsonschema + Pillow |
| 本地 OCR 复核 | Tesseract（可选，缺失时保留 gap） |
| 剪映工程组装 | Mac 剪映专业版 + 本地脚本 |
| 内部预览 MP4 | FFmpeg |

**一句话：只要你的 AI Agent 能看视频、能写文案，基础版就能跑通。**

### 🚀 完整版（进阶扩展）

在基础版之上，如需**自动生成视频素材**，需要额外配置：

| 扩展能力 | 需要 |
|---------|------|
| AI 视频生成（替换 placeholder 素材） | LibTV / 可灵 / 其他视频生成 API |
| AI 配音生成 | TTS API（如豆包、阿里云等） |

**这些扩展默认关闭，需要你对当前操作显式授权才会调用。**

---

## 一个完整案例：眼镜店视频

### 输入

- **参考视频**：一条杭州眼镜店的抖音视频（约 64 秒，17 个镜头）
- **门店信息**：
  - 店名：澄明眼镜青禾路店
  - 城市：杭州
  - 核心产品：青少年近视防控验配、成人渐进多焦点镜片
  - 人物角色：主理验光师林岚

### 处理

AI Agent 分析参考视频后，逆向拆解出 17 个镜头的结构：

| 镜头 | 类型 | 功能 |
|------|------|------|
| shot_001 | 人物口播 | 开场建立信任 |
| shot_002-004 | 产品 B-roll | 展示验光设备 |
| ... | ... | ... |
| shot_017 | 结尾行动号召 | 引导到店 |

每个镜头都配有：
- **拍摄指导**：机位、景别、动作建议
- **文案方向**：口播内容或画面配字
- **时长目标**：精确到毫秒

### 输出

交付包包含：

```
delivery/
  README.md                    ← 使用指南
  storyboard/storyboard.md     ← 完整故事板
  previs/index.html            ← 可浏览的预演页面
  content/
    copy_script.json           ← 可修改文案
    voiceover_script.json      ← 配音脚本
  subtitles/
    subtitles.vtt              ← 字幕文件
    word_timestamps.json       ← 词级时间轴
  audio/
    audio_mix_plan.json        ← 音频混合计划
  jianying_manifest/           ← 剪映工程配置
  internal_preview.mp4         ← 内部预览视频
```

剪映打开后，看到：
- 17 段视频时间线
- 17 条可编辑字幕
- 1 条配音音频轨
- 所有素材可替换、可修改

---

## 安装

### 1. 安装成 Codex Skill

```bash
git clone https://github.com/zkbys/reverse-editing.git
mkdir -p ~/.codex/skills
cp -R reverse-editing/skills/reverse-editing-workflow ~/.codex/skills/
```

### 2. 本机依赖

```bash
pip install -r requirements.txt
# 需要本机已有 ffmpeg 和 ffprobe
# Tesseract 可选，缺失时 OCR 步骤会跳过
```

### 3. 调用

```text
Use $reverse-editing-workflow to process this reference as a safe local editable workflow package. Keep download, LibTV, TTS, OCR installation, and Jianying writes disabled until I explicitly authorize it.
```

---

## 安全边界

- 不下载、不生成、不修改剪映草稿，除非你**当前操作显式授权**
- 不上传任何真实视频、素材或工程文件
- 所有产物标记为 `internal_preview`，不是 `publish_ready`

---

## License

MIT
