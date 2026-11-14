# 东方红雾录

> 一款致敬《东方红魔乡》的 2D 弹幕射击游戏。用 Python + pygame-ce 从零实现碰撞检测、关卡状态机与数据驱动的符卡系统，三关完整流程可通关。

---

## 🎮 游戏截图

<!-- 截图：替换为你自己的游戏画面 -->
<p align="center">
  <img src=".github/screenshots/title.png" width="48%" alt="标题画面">
  <img src=".github/screenshots/gameplay.png" width="48%" alt="战斗画面">
</p>
<p align="center">
  <img src=".github/screenshots/spellcard.png" width="48%" alt="符卡战">
  <img src=".github/screenshots/gallery.png" width="48%" alt="人物录">
</p>

## ✨ 特色

- **三关完整流程**：人里近郊 → 雾之湖 → 红魔馆，每关依次经过过场对话、杂兵波次、中 Boss、关底 Boss 与关卡结算，第三关为终局。
- **数据驱动的符卡系统**：扇形 / 环形 / 螺旋 / 散射四种发射器自由组合，每张符卡独立冷却与限时，贴近原作的「取得」判定（限时内无受击、无灵击才算取得）。
- **自研碰撞检测**：不依赖物理引擎，自行实现圆-圆、线段-圆扫掠与均匀空间网格，支持 F2 调试层可视化命中圆、擦弹圆与扫掠线段。
- **原作风味的 UI**：标题复用红魔乡标题图与 `project-striker` 菜单字图，战斗采用 1280×960 横屏布局（左侧弹幕场、右侧信息栏），哥特描金边框 + 绯红页签。
- **人物录与日后谈**：通关后解锁 7 名角色立绘与台词浏览，以及三页原作口吻的后记与鸣谢。
- **跨平台打包**：CI 自动构建 Windows / Linux / macOS 可执行文件，开箱即玩。

## 🕹️ 操作

| 按键 | 功能 |
|---|---|
| ↑ ↓ / Enter | 标题菜单选择与确认 |
| ← → | 说明书翻页 / 人物录切换 |
| 方向键 / WASD | 自机移动 |
| Shift | 低速移动（显示判定点） |
| Z | 射击（点按单发 / 按住连发） |
| X | 灵击（Bomb，消弹并短时无敌） |
| F1 | 暂停 / 继续 |
| F2 | 碰撞调试层 |
| F3 | 无敌模式 |
| R | 结算后重新开始 |
| Esc | 返回标题 / 退出 |

## 📥 下载

前往 [Releases](https://github.com/lyra-xuan/Touhou_Project/releases) 页面下载对应平台的可执行文件，解压后双击运行即可，无需安装 Python。

## 🛠️ 从源码运行

需要 Python 3.12。

```powershell
# 克隆仓库
git clone https://github.com/lyra-xuan/Touhou_Project.git
cd Touhou_Project

# 创建虚拟环境
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
python -m pip install -r requirements.txt

# 运行
python main.py
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 📦 打包为可执行文件

```bash
pip install -r requirements-build.txt
bash build.sh
```

产物在 `dist/` 目录下。CI 配置见 [.github/workflows/build.yml](.github/workflows/build.yml)。

## 📁 项目结构

```text
main.py                 程序入口
src/
  config.py             窗口与玩法参数
  director.py           关卡推进状态机（过场/对话/波次/战斗/结算）
  stages.py             三关剧本与步骤数据
  waves.py              杂兵波次编队
  dialogue.py           立绘对话场景
  spells.py             发射器与符卡定义（数据驱动）
  entities.py           玩家、Boss、妖精、子弹、道具、特效
  collision.py          几何碰撞与空间网格
  art.py                背景、角色、弹幕、特效图片加载
  audio.py              音效与背景音乐（失败时静默降级）
  game.py               输入、游戏循环、碰撞与渲染
assets/                 战斗素材、音效、背景音乐、标题图（含来源说明）
tests/                  回归测试
docs/                   需求、制作指南、素材清单
```

## 🧰 技术栈

- **Python 3.12** + **pygame-ce**（图形 / 输入 / 音频）
- 自研碰撞检测：圆-圆、AABB、线段-圆扫掠、均匀空间网格
- 数据驱动符卡：声明式 `Emitter` + `SpellCard` 组合
- 关卡状态机：`StageDirector` 驱动剧本步骤序列
- **PyInstaller** 单文件打包 + **GitHub Actions** 跨平台 CI

## 🙏 素材与许可

本项目为致敬《东方红魔乡》的非商业同人作品。游戏中使用的东方角色、立绘、背景、弹幕与特效素材来自东方红魔乡原作，背景音乐为 PC-98 时期东方原曲的转码版本。各素材的具体来源与许可说明见：

- `assets/title/ATTRIBUTION.md`
- `assets/gameplay/ATTRIBUTION.md`
- `assets/audio/ATTRIBUTION.md`
- `assets/bgm/ATTRIBUTION.md`

本项目代码部分按个人偏好授权，仅供学习交流，请勿用于商业用途。

---

<p align="center">
  <sub>Made with ♥ — 东方红雾录 · Scarlet Mist Record</sub>
</p>
