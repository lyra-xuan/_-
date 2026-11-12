# 弹幕射击：碰撞检测实践

《问题求解》课程大作业。使用 Python 和 pygame-ce 开发 2D 弹幕射击游戏，不使用 Unity、Godot 等游戏引擎。项目重点是可解释、可演示的碰撞检测。

## 当前进度

当前版本包含标题菜单、操作说明页和可运行的单 Boss 战斗流程：

- 开始游戏、查看操作说明、退出游戏。
- 玩家移动、Shift 低速移动、暂停与退出。
- Z 点按单发、按住连发；Boss 往返移动并在半血切换两种弹幕。
- Boss 血条、玩家生命、命中/擦弹计数，以及胜利和失败流程。
- 玩家有 3 条命；受击后重生、清空当前敌弹并获得 1.5 秒无敌时间。
- 失败后可按 R 重开，或按 Enter / Esc 返回标题页。
- AABB、圆-圆、线段-圆扫掠检测和均匀空间网格工具。
- 玩家/敌弹和玩家弹/Boss 的相对运动连续碰撞检测。

项目目标是一关一 Boss。分数系统、碰撞调试可视化和完整美术仍待制作。标题页复用已获许可的东方红魔乡标题图与 `project-striker` 菜单字图，来源和许可记录见 `assets/title/ATTRIBUTION.md`；战斗中的玩家、Boss 和弹幕仍由程序绘制。

游戏采用 1280×960 的 4:3 横屏布局，参考 `project-striker` 的画布尺寸。

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
| R | 胜利或失败后重新开始 |
| Enter / Esc | 失败后返回标题页 |
| Esc | 标题页退出；操作说明页返回；普通战斗中退出 |

## 目录

```text
main.py                 程序入口
src/config.py           窗口和玩法参数
src/entities.py         玩家、子弹等实体
src/collision.py        几何碰撞与空间网格
src/game.py             输入、游戏循环、碰撞和渲染
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
