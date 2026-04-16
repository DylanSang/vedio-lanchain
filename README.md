# 主题-方案-视频-平台发布 自动化工作流

基于 Python + LangChain 构建的全自动化短视频工作流系统。从飞书消息触发 → 爆点分析 → AI 内容方案 → TTS配音+BGM → 视频生成 → 剪辑评估 → 品牌标识 → 多平台适配发布 → 数据回收。

## 架构概览

```
飞书消息 → 飞书Bot(WebSocket) → Orchestrator(17步全流程)
  ├── Step 1: 专家+创意师爆点分析 (LLM)
  ├── Step 1.5: 用户确认交互 (无爆点时)
  ├── Step 2: AI内容方案生成 (多视角变体)
  ├── Step 3: 方案导出 .md 文件
  ├── Step 4: 视频批量生成 (即梦API/小云雀)
  ├── Step 5: TTS配音生成 (Edge-TTS)
  ├── Step 6: BGM匹配 (素材库+LLM推荐)
  ├── Step 7: 音频处理链 (混音/归一化/降噪)
  ├── Step 8: 字幕生成+烧录 (SRT/ASS)
  ├── Step 9: 资深剪辑师评估 (8维度AI评分+FFmpeg)
  ├── Step 10: 品牌标识 (片头/片尾/水印)
  ├── Step 11: 封面图生成 (抽帧+文字合成)
  ├── Step 12: 多尺寸视频适配 (9:16/16:9/3:4)
  ├── Step 13: 平台文案适配 (LLM差异化改写)
  ├── Step 14: 内容合规审查 (敏感词+平台规则)
  ├── Step 15: 定时发布调度 (黄金时间+多账号+重试+草稿箱)
  ├── Step 16: 飞书结果回报 (由定时回调触发)
  └── Step 17: 数据回收调度 (24h/48h/7d)
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填写飞书、LLM、火山引擎等 API 密钥
```

### 3. 准备素材

```bash
# 将 BGM 文件放入对应风格目录
assets/bgm/科技/
assets/bgm/温馨/
assets/bgm/激昂/

# 将品牌素材放入模板目录
assets/templates/intro/    # 片头视频/图片
assets/templates/outro/    # 片尾视频/图片
assets/templates/watermark/ # 水印图片

# 将中文字体放入字体目录 (可选)
assets/fonts/
```

### 4. 启动

```bash
python bot.py
```

### 5. 在飞书群中发送指令

```
#视频 AI编程教程 [视角数:3] [平台:抖音,B站,小红书] [风格:科技感]
```

参数均用方括号包裹，可省略（使用默认值）：
```
#视频 量子计算入门                      — 仅主题, 其余使用默认
#视频 Python爬虫 [视角数:2] [引擎:即梦]  — 部分参数
```

交互指令（爆点分析后无爆点时）：
```
#确认 {workflow_id}            — 坚持原主题
#换主题 {workflow_id} 新主题名   — 更换为自定义主题
#推荐1 {workflow_id}           — 选择推荐列表中第1个主题
```

## 技术栈

| 模块 | 技术方案 |
|------|---------|
| 飞书接入 | lark-oapi WebSocket 长连接 |
| AI 编排 | LangChain + ChatOpenAI |
| 视频生成 | 火山引擎即梦 API / 小云雀 Playwright |
| TTS 配音 | Edge-TTS (免费多音色) |
| BGM | 本地素材库 + LLM 推荐 |
| 音视频处理 | FFmpeg (混音/字幕/转场/裁剪/水印) |
| 封面图 | FFmpeg 抽帧 + Pillow 文字合成 |
| 定时发布 | APScheduler |
| 数据存储 | SQLite |
| 平台发布 | 各平台 Open API + Playwright |

## 项目结构

```
aiLanChain/
├── bot.py                           # 入口: 飞书 Bot 启动
├── config.py                        # 配置管理
├── models/
│   ├── schemas.py                   # Pydantic 数据模型
│   └── database.py                  # SQLite ORM
├── services/
│   ├── orchestrator.py              # 17步全流程编排
│   ├── topic_analyst.py             # 爆点分析
│   ├── content_planner.py           # 内容方案生成
│   ├── plan_exporter.py             # 方案导出 .md
│   ├── video_generator.py           # 视频批量生成
│   ├── jimeng_client.py             # 即梦 API
│   ├── xiaoyunque_bot.py            # 小云雀自动化
│   ├── tts_service.py               # TTS 配音
│   ├── bgm_matcher.py              # BGM 匹配
│   ├── audio_mixer.py              # 音频处理链
│   ├── subtitle_generator.py       # 字幕生成+烧录
│   ├── video_editor.py             # 剪辑师评估
│   ├── brand_overlay.py            # 品牌标识
│   ├── thumbnail_generator.py      # 封面图生成
│   ├── video_adapter.py            # 多尺寸适配
│   ├── copy_adapter.py             # 文案适配
│   ├── compliance_checker.py       # 合规审查
│   ├── publish_scheduler.py        # 定时发布
│   ├── retry_handler.py            # 重试+草稿箱
│   ├── account_manager.py          # 多账号矩阵
│   ├── asset_library.py            # 素材库管理
│   ├── analytics_collector.py      # 数据回收
│   ├── feishu_notifier.py          # 飞书通知
│   └── publisher/                   # 发布器
│       ├── base.py / douyin.py / bilibili.py
│       ├── xiaohongshu.py / kuaishou.py / wechat_video.py
│       └── __init__.py
├── assets/
│   ├── bgm/                        # BGM 素材库
│   ├── fonts/                       # 字体文件
│   └── templates/{intro,outro,watermark}/
├── output/
│   ├── plans/                       # 方案 .md
│   ├── videos/                      # 视频缓存
│   ├── audio/                       # 音频缓存
│   ├── thumbnails/                  # 封面图
│   └── drafts/                      # 发布草稿箱
├── tests/                           # 单元测试
├── .env.example
├── requirements.txt
└── README.md
```

## 核心工作流详细说明

### 后期制作管线 (Step 5-10)

每个视角变体的视频经过以下处理:

1. **TTS 配音**: 分镜旁白 → Edge-TTS → 按时间轴对齐的音频段
2. **BGM 匹配**: LLM 分析方案情绪 → 匹配素材库 BGM
3. **音频混音**: TTS + BGM ducking 混音 → loudnorm 归一化 (-16 LUFS)
4. **字幕烧录**: TTS 时间戳 → ASS 花字字幕 → FFmpeg 硬烧
5. **剪辑评估**: AI 8 维度评分 → FFmpeg 滤镜链优化
6. **品牌标识**: 片头(2-3s) + 全程水印 + 片尾(3-5s)

### 平台适配 (Step 11-14)

- **封面图**: 智能抽帧 + 标题合成 + 各平台尺寸裁切
- **视频尺寸**: 9:16 竖屏 / 16:9 横屏 / 3:4 小红书 (高斯模糊背景)
- **文案改写**: 抖音 hook / B站信息流 / 小红书 emoji 种草
- **合规审查**: 敏感词 + 平台规则 (抖音禁微信引流等)

### 运营增强 (Step 15-17)

- **定时发布**: 各平台黄金时间 (抖音 18-20 / B站 17-19 / 小红书 20-22)
- **失败重试**: 指数退避 2s→4s→8s, 最终失败保存草稿箱
- **数据回收**: 发布后 24h/48h/7d 自动采集播放/互动数据
- **A/B 对比**: 同主题多视角变体效果对比, 反哺选题优化

## 运行测试

```bash
pytest tests/ -v
```
# vedio-lanchain
