# 弹幕射击：碰撞检测实践

《问题求解》课程大作业。使用 Python 和 pygame-ce 开发 2D 弹幕射击游戏，不使用 Unity、Godot 等游戏引擎。项目重点是可解释、可演示的碰撞检测。

## 当前进度

当前版本是可运行的核心原型，包含：

- 玩家移动、Shift 低速移动、暂停与退出。
- 环形/扇形弹幕生成与擦弹、命中计数。
- AABB、圆-圆、线段-圆扫掠检测和均匀空间网格工具。
- 玩家与子弹相对运动的连续碰撞检测。

完整功能范围仍待确认。当前不包含菜单、关卡流程、Boss、玩家攻击和完整美术资源。

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
| 方向键 / WASD | 移动 |
| Shift | 低速移动，便于躲避弹幕 |
| P / 空格 | 暂停或继续 |
| Esc | 退出 |

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
- 外部图像、音效和字体须记录来源与许可；未确认风格前不加入最终素材。

详细范围见 [功能需求](docs/requirements.md)、[制作与监督指南](docs/production-guide.md) 和 [素材需求](docs/assets.md)。
