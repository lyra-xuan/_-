# 弹幕射击：碰撞检测实践

《问题求解》课程大作业。使用 Python 和 pygame-ce 开发 2D 弹幕射击游戏，不使用 Unity、Godot 等游戏引擎。项目重点是可解释、可演示的碰撞检测。

## 当前进度

当前版本包含标题菜单、操作说明页和可运行的单 Boss 战斗流程：

- 开始游戏、查看操作说明、退出游戏。
- 玩家移动、Shift 低速移动、暂停与退出。
- Z 点按单发、按住连发；Boss 往返移动并在半血切换两种弹幕。
- 阶段 1 五发瞄准扇形小玉，阶段 2 大玉环 + 交错小玉双层环形弹幕；符卡限时 45 秒，超时强制推进。
- 计分与最高分持久化（`hiscore.txt`）：擦弹 +500、过阶段 +5000、击破 +10000。
- 弹幕场三层渲染（关卡背景 + 暗红薄罩 + 径向暗角）；自机按移动方向切换帧组并显示低速判定点。
- 命中火花、擦弹星环、受击与击破大爆特效；Boss 立绘随阶段切换并受击闪白。
- 飘落的装饰性小妖精（纯视觉，不参与碰撞）。
- 音效：发射、命中、擦弹、警报、死亡、阶段切换与菜单操作；无音频设备时自动静音。
- Boss 血条、符卡条（名称/段数/倒计时）、玩家生命、得分、擦弹/敌弹计数，以及胜利和失败结算插图。
- 玩家有 3 条命；受击后重生、清空当前敌弹并获得 1.5 秒无敌时间。
- 失败后可按 R 重开，或按 Enter / Esc 返回标题页。
- 1280×960 横屏战斗布局：左侧弹幕场、右侧 Boss 与战斗信息栏。
- 使用已获许可的东方红魔乡背景、自机、Boss 立绘、弹幕、特效与音效素材。
- AABB、圆-圆、线段-圆扫掠检测和均匀空间网格工具。
- 玩家/敌弹和玩家弹/Boss 的相对运动连续碰撞检测。
- F2 碰撞调试层：空间网格、双层判定圆、敌弹扫掠线段与当帧候选/命中统计。

项目目标是一关一 Boss。标题页复用东方红魔乡标题图与 `project-striker` 菜单字图；战斗画面使用用户提供并确认许可的东方红魔乡素材。素材来源和许可说明分别见 `assets/title/ATTRIBUTION.md`、`assets/gameplay/ATTRIBUTION.md` 与 `assets/audio/ATTRIBUTION.md`。

游戏采用 1280×960 的 4:3 横屏布局，参考 `project-striker` 的画布尺寸与左侧弹幕场、右侧状态栏的布局。

## 环境与运行

建议使用 Python 3.12。Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

运行自动化测试：

```powershell
python -m unittest discover -s tests -v
```

## 操作

| 按键 | 功能 |
|---|---|
| ↑ / ↓，Enter | 标题页选择与确认 |
| 方向键 / WASD | 移动 |
| Shift | 低速移动，便于躲避弹幕 |
| Z | 点按单发，按住连续射击 |
| F1 | 暂停或继续 |
| F2 | 开关碰撞调试层（默认关闭） |
| R | 胜利或失败后重新开始 |
| Enter / Esc | 失败后返回标题页 |
| Esc | 标题页退出；操作说明页返回；普通战斗中退出 |

## 目录

```text
main.py                 程序入口
src/config.py           窗口和玩法参数
src/entities.py         玩家、Boss、子弹、妖精与特效实体
src/collision.py        几何碰撞与空间网格
src/art.py              战斗背景、角色、弹幕与特效图片加载
src/audio.py            音效加载与播放（失败时静默降级）
src/game.py             输入、游戏循环、碰撞和渲染
assets/gameplay/        战斗背景、自机、Boss、弹幕与特效素材
assets/audio/           音效素材
tests/                  回归测试
docs/requirements.md    功能范围和验收标准
docs/production-guide.md 开发阶段与协作监督方式
docs/assets.md          素材清单与风格选择
```

## 项目约束

- 使用 pygame-ce 作为底层图形与输入库，不引入游戏引擎。
- 碰撞检测由项目代码实现；几何算法是课程展示重点。
- 外部图像、音效和字体须记录来源与许可；未核实许可前不加入游戏或仓库。

详细范围见 [功能需求](docs/requirements.md)、[制作与监督指南](docs/production-guide.md) 和 [素材需求](docs/assets.md)。
