"""三关剧本：波次编排、中 Boss / 关底 Boss 与剧情衔接。

沿用原作红魔乡的推进节奏——「杂兵波次 → 中 Boss → 关底 Boss」——但把原作
六关压缩成三关，并在每关的入场、遭遇与击破处插入剧情对话，让三关连成一条
完整的异变调查线：

    第一关  红雾笼罩的人里近郊，撞见夜之妖怪「露米娅」
    第二关  红雾最浓的雾之湖，与冰之妖精「琪露诺」交手
    第三关  红魔馆内部，依次突破门卫、魔女、女仆长，直到馆主蕾米莉亚

每个 ``StageScript`` 会被展开成一串步骤（见文件末尾的 ``Banner`` / ``Talk``
/ ``Waves`` / ``Fight`` / ``Clear``），由 ``director.StageDirector`` 逐条执行。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .dialogue import Line, Scene
from .spells import STAGE_BOSS_SPECS, BossSpec, Emitter, MIDBOSS_SPECS
from .waves import WaveSpec

# --------------------------------------------------------------------------- #
# 杂兵弹型：小妖精打三向瞄准弹，大妖精打环形封路弹
# --------------------------------------------------------------------------- #
FAN_THREE = Emitter(kind="fan", interval=2.10, count=3, step=14.0,
                    speed=185.0, bullet="small_blue", aim=True)
FAN_FIVE = Emitter(kind="fan", interval=2.50, count=4, step=11.0,
                   speed=195.0, bullet="small_red", aim=True)
RING_FOUR = Emitter(kind="ring", interval=2.60, count=3, speed=145.0,
                    bullet="mid_white")
RING_SIX = Emitter(kind="ring", interval=2.90, count=5, speed=160.0,
                   bullet="large_cyan")
SPIRAL_SLIM = Emitter(kind="spiral", interval=0.65, count=1, speed=175.0,
                      spin=21.0, bullet="small_green")


# --------------------------------------------------------------------------- #
# 步骤：把关卡脚本切成「过场 / 对话 / 波次 / 战斗 / 结算」五种
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Banner:
    """关卡标题过场。"""

    stage_index: int
    title: str
    subtitle: str
    duration: float = config.STAGE_BANNER_DURATION


@dataclass(frozen=True)
class Talk:
    """一段剧情对话。"""

    scene: Scene


@dataclass(frozen=True)
class Waves:
    """一串杂兵波次。"""

    waves: tuple[WaveSpec, ...]


@dataclass(frozen=True)
class Fight:
    """一场 Boss 战（中 Boss 或关底 Boss）。"""

    spec: BossSpec


@dataclass(frozen=True)
class Clear:
    """一关结束的停留。"""

    stage_index: int
    duration: float = config.STAGE_CLEAR_DELAY


@dataclass(frozen=True)
class StageScript:
    """一关的完整描述。"""

    index: int
    title: str
    subtitle: str
    background: int                      # art.stage_backgrounds 下标
    enemy_small: str                     # art.enemy_frames 键，杂兵小型
    enemy_large: str                     # art.enemy_frames 键，杂兵大型
    waves: tuple[WaveSpec, ...]
    boss: BossSpec                       # 关底首领
    midboss: BossSpec | None = None
    intro: Scene | None = None
    midboss_pre: Scene | None = None     # 中 Boss 登场前的对话
    boss_pre: Scene | None = None
    boss_post: Scene | None = None

    def steps(self) -> tuple:
        script: list = [Banner(self.index, self.title, self.subtitle)]
        if self.intro is not None:
            script.append(Talk(self.intro))
        script.append(Waves(self.waves))
        if self.midboss is not None:
            if self.midboss_pre is not None:
                script.append(Talk(self.midboss_pre))
            script.append(Fight(self.midboss))
        if self.boss_pre is not None:
            script.append(Talk(self.boss_pre))
        script.append(Fight(self.boss))
        if self.boss_post is not None:
            script.append(Talk(self.boss_post))
        script.append(Clear(self.index))
        return tuple(script)


# --------------------------------------------------------------------------- #
# 第一关：红雾下的人里近郊
# --------------------------------------------------------------------------- #
_STAGE1_WAVES = (
    WaveSpec(formation="line", count=5, frames="small1", spread=0.16,
             delay=0.4),
    WaveSpec(formation="arc", count=4, frames="small1", spread=0.28,
             attack=FAN_THREE),
    WaveSpec(formation="sides", count=5, frames="small1", spread=0.30,
             sway=34.0),
    WaveSpec(formation="column", count=2, frames="large1", hp=90.0,
             hover_y=config.PLAYFIELD_TOP + 250.0, hover_time=3.2,
             speed=110.0, sway=44.0, drop="power", attack=RING_FOUR),
    WaveSpec(formation="vee", count=6, frames="small1", spread=0.22,
             attack=FAN_THREE),
    WaveSpec(formation="chase", count=5, frames="large1", hp=70.0,
             speed=95.0, sway=30.0, attack=FAN_FIVE),
)

_STAGE1_INTRO = Scene(
    title="人里近郊",
    lines=(
        Line("reimu", "又是红雾。今年的雾比往年都浓，连透过来的月光都被染成了暗红色，人里的灯火隔着雾看起来像是快要熄灭的余烬。", 0),
        Line("reimu", "沿着雾的流向往上游走，源头大概在雾之湖的方向——不过在那之前，先去人里转一圈，确认一下情况再说。", 1),
        Line("reimu", "要是连人里的灯都灭光了，那可就不只是「异变」两个字能打发的了。博丽神社的赛钱箱，可经不起第三次红雾的折腾。", 2),
        Line("reimu", "……说起来，这次的雾里好像还混着什么别的味道。算了，先往前走，见到谁就问谁吧。", 0),
    ),
)

_STAGE1_MIDBOSS_PRE = Scene(
    title="夜之暗影",
    lines=(
        Line("rumia", "呀——是外面的人类！这么晚了还一个人在外面走，不知道夜里很危险的吗？还是说，你是特地来当我的晚饭的？", 0, "right"),
        Line("reimu", "危险的妖怪正站在我面前跟我聊天，这事本身就够危险的了。话说回来，你就是把这片雾弄暗的家伙吧？", 1),
        Line("rumia", "雾？那不是我弄的啦，我只是刚好喜欢暗一点的地方而已。不过既然你送上门来——闇符「黑暗侧之月」，就让你尝尝伸手不见五指的滋味！", 1, "right"),
    ),
)

_STAGE1_BOSS_PRE = Scene(
    title="雾中遭遇",
    lines=(
        Line("rumia", "呜……好亮、好痛！你居然能在我的黑暗里还看得这么清楚，博丽的巫女都这么不讲道理的吗？", 1, "right"),
        Line("reimu", "博丽的巫女要是被一点黑雾就蒙住眼睛，那早就失业了。倒是你，躲在雾里偷袭人，这才叫不讲道理吧。", 0),
        Line("rumia", "哼！那就让你见识一下我真正的力量吧！我的特殊技能可不只有「黑暗侧之月」而已——", 1, "right"),
        Line("rumia", "夜符「夜雀」、还有闇符「分界」！这两招连在一起，你要是还能躲过去，我今晚就真的不吃你了！", 0, "right"),
    ),
)

_STAGE1_BOSS_POST = Scene(
    title="雾散之处",
    lines=(
        Line("rumia", "呜……太亮了，眼睛好痛。算了算了，今晚就到这里吧，我认输还不行吗。", 0, "right"),
        Line("rumia", "不过我提醒你哦，前面还有比我更麻烦的家伙在等着呢。湖面上的雾比这里还厚，小心走着走着就迷路啦。", 1, "right"),
        Line("reimu", "更麻烦的家伙吗……嘛，反正来都来了。", 0),
        Line("reimu", "雾在一点点往湖的方向退，看来这只是第一站。红雾啊红雾，你到底想把幻想乡变成什么样子。", 1),
    ),
)


# --------------------------------------------------------------------------- #
# 第二关：雾之湖
# --------------------------------------------------------------------------- #
_STAGE2_WAVES = (
    WaveSpec(formation="arc", count=5, frames="small2", spread=0.20,
             delay=0.4, attack=FAN_THREE),
    WaveSpec(formation="chase", count=5, frames="small2", speed=82.0,
             spread=0.24, attack=FAN_THREE),
    WaveSpec(formation="line", count=4, frames="large2", hp=100.0,
             hover_y=config.PLAYFIELD_TOP + 220.0, hover_time=3.6,
             speed=105.0, drop="power", attack=RING_SIX),
    WaveSpec(formation="sides", count=6, frames="small2", sway=40.0,
             spread=0.26, attack=FAN_THREE),
    WaveSpec(formation="vee", count=5, frames="large2", hp=80.0, speed=92.0,
             attack=RING_FOUR),
)

_STAGE2_INTRO = Scene(
    title="雾之湖",
    lines=(
        Line("reimu", "雾到这里就厚得几乎看不见对岸了，连脚下的路都要靠摸索才敢往前挪。", 0),
        Line("reimu", "水面上居然结了薄冰——这可是夏天啊，哪来的冰？红雾、结冰、还有不知分寸的妖怪，今晚真是一个比一个离谱。", 1),
        Line("reimu", "再往前的话，雾估计会浓得连弹幕都看不清。不过嘛，反正弹幕看不清归看不清，该躲还是得躲，该退治还是得退治。", 0),
    ),
)

_STAGE2_MIDBOSS_PRE = Scene(
    title="冰之妖精",
    lines=(
        Line("cirno", "站住站住站住！这里可是我——雾之湖最强的冰之妖精琪露诺的地盘！没有我的允许，谁都不准过去！", 0, "right"),
        Line("reimu", "最强的地盘？听起来像是自己给自己颁发的奖状嘛。话说回来，湖上的冰是你弄的？", 0),
        Line("cirno", "当、当然是我弄的！整个雾之湖的冰全都是我冻的！你、你瞧不起谁呢！", 0, "right"),
        Line("cirno", "冰符「冰柱坠落」——看好了，这就是最强的冰冻弹幕！冻成冰块可别怪我没提醒你！", 0, "right"),
    ),
)

_STAGE2_BOSS_PRE = Scene(
    title="雾之湖的主人",
    lines=(
        Line("cirno", "唔……冰碎掉了。不过没关系，刚才的「冰柱坠落」只是开胃小菜而已！真正的实力现在才要开始！", 0, "right"),
        Line("reimu", "最强的一招？你刚才已经说过好几遍「最强」这两个字了吧。", 1),
        Line("cirno", "哼！那是因为我真的很强嘛！看好了，我的特殊技能有两招——", 0, "right"),
        Line("cirno", "雹符「冰雹风暴」和雪符「钻石暴风雪」！这两招连在一起，一定会把你冻成冰棍的！我可是雾之湖最强的！", 0, "right"),
    ),
)

_STAGE2_BOSS_POST = Scene(
    title="湖面重归",
    lines=(
        Line("cirno", "唔……冰又碎了。不过、不过我才没有输！我只是……只是有点冷了而已！对，就是冷了！", 0, "right"),
        Line("reimu", "是是是，你最强你最强。好了好了，雾开始退了。", 0),
        Line("reimu", "雾气退去的方向，是那座洋馆——红魔馆。看来异变的源头果然在那里。", 1),
        Line("reimu", "穿过这座湖，就是洋馆的大门了。门口的门卫、馆里的魔女和女仆长……今晚大概都在等着我吧。", 2),
    ),
)


# --------------------------------------------------------------------------- #
# 第三关：红魔馆
# --------------------------------------------------------------------------- #
_STAGE3_WAVES = (
    WaveSpec(formation="line", count=5, frames="small3", spread=0.18,
             delay=0.4, attack=FAN_THREE),
    WaveSpec(formation="vee", count=6, frames="small3", spread=0.20,
             attack=FAN_FIVE),
    WaveSpec(formation="column", count=3, frames="large3", hp=110.0,
             hover_y=config.PLAYFIELD_TOP + 200.0, hover_time=3.8,
             speed=100.0, drop="power", attack=RING_SIX),
    WaveSpec(formation="chase", count=5, frames="small3", speed=90.0,
             spread=0.22, attack=SPIRAL_SLIM),
    WaveSpec(formation="sides", count=6, frames="large3", hp=90.0,
             speed=96.0, attack=RING_FOUR),
    WaveSpec(formation="arc", count=6, frames="small3", spread=0.20,
             attack=FAN_FIVE),
)

_STAGE3_INTRO = Scene(
    title="红魔馆",
    lines=(
        Line("reimu", "好大的洋馆。红雾就是从这里的窗户和烟囱里涌出来的，浓得像是整座馆都在冒烟。", 0),
        Line("reimu", "门口那个中国来的门卫已经被我打发去打瞌睡了，图书馆里的魔女也熄了火，走廊上能用小刀停住时间的女仆长也被我劝回去了。", 1),
        Line("reimu", "说实话，一路打上来还挺累的。不过再怎么说，也不该把红雾盖满整个幻想乡——人里的灯都快灭光了。", 2),
        Line("reimu", "敲门太麻烦了，反正门也没锁。直接从正门进去吧。", 3),
        Line("reimu", "馆主小姐，你最好给我一个说得过去的理由。不然的话，今晚的赛钱箱可就有着落了。", 4),
    ),
)

_STAGE3_BOSS_PRE = Scene(
    title="红色馆主",
    lines=(
        Line("remilia", "哎呀，稀客。博丽的巫女居然会主动登门拜访，这可真是难得。咲夜，去泡壶红茶来。", 0, "right"),
        Line("reimu", "门卫、魔女、女仆长——你手下的人我都见过了。把红雾收回去吧，人里的灯都快灭光了。", 0),
        Line("remilia", "灯灭了又有什么要紧？我只是想看看红色的月亮而已。活了五百年，普通的月亮早就看腻了。", 0, "right"),
        Line("reimu", "红色的月亮？", 2),
        Line("remilia", "把雾染成红色，让月光透过来，不就是红色的月亮了吗？多浪漫的想法，你不觉得吗？", 0, "right"),
        Line("reimu", "所以你就把整个幻想乡都罩进了雾里？就为了看一眼红色的月亮？", 3),
        Line("remilia", "难得有客人上门，总该有点招待才是。让我用符卡来一场像样的问候吧——这可是红魔馆的待客之道。", 0, "right"),
        Line("remilia", "我的特殊技能有五张符卡：红符「猩红射击」、红魔法「红色魔术」、冥符「红色的冥界」、神罚「年幼的恶魔之王」，还有最后的神枪「冈格尼尔之枪」。", 0, "right"),
        Line("remilia", "五百年的力量，今晚就全部用来招待你了。可别太快就倒下哦，巫女小姐。", 0, "right"),
        Line("reimu", "五张符卡吗……嘛，反正来都来了。那我就把这场问候，原样退回去。准备好了的话，就开始吧。", 4),
    ),
)

_STAGE3_BOSS_POST = Scene(
    title="异变终结",
    lines=(
        Line("remilia", "呵……打得不错嘛，博丽的巫女。看来咲夜她们输得不冤。", 0, "right"),
        Line("remilia", "红雾我已经收了。月亮又变回了单调的苍白色，真是无趣。不过看在你打得这么尽兴的份上，这次就饶了你。", 0, "right"),
        Line("reimu", "下次想赏月的话，找间没人的山丘搭个观星台就行，别再把整个幻想乡都卷进来了。", 0),
        Line("remilia", "说得轻巧。我可受不了那些人类渔夫大惊小怪的目光。", 0, "right"),
        Line("reimu", "那你就在自家院子里搭一个嘛，红魔馆的院子那么大，总够用了。", 1),
        Line("remilia", "……这个主意倒是不错。下次让咲夜去办。", 0, "right"),
        Line("remilia", "记住了，巫女。下次我会准备得更有趣一点，到时候可别哭着喊着要回家哦。", 0, "right"),
        Line("reimu", "我可不想再有下次。不过……今晚的月亮，确实挺好看的。", 2),
        Line("reimu", "幻想乡总算又能好好睡一觉了。回去吧，明天还有一堆杂事要处理呢。", 3),
    ),
)


STAGES: tuple[StageScript, ...] = (
    StageScript(
        index=1,
        title="紅霧の麓",
        subtitle="Scarlet Mist  /  Stage 1",
        background=0,
        enemy_small="small1",
        enemy_large="large1",
        waves=_STAGE1_WAVES,
        midboss=MIDBOSS_SPECS["rumia"],
        boss=STAGE_BOSS_SPECS["rumia"],
        intro=_STAGE1_INTRO,
        midboss_pre=_STAGE1_MIDBOSS_PRE,
        boss_pre=_STAGE1_BOSS_PRE,
        boss_post=_STAGE1_BOSS_POST,
    ),
    StageScript(
        index=2,
        title="霧の湖",
        subtitle="Misty Lake  /  Stage 2",
        background=1,
        enemy_small="small2",
        enemy_large="large2",
        waves=_STAGE2_WAVES,
        midboss=MIDBOSS_SPECS["cirno"],
        boss=STAGE_BOSS_SPECS["cirno"],
        intro=_STAGE2_INTRO,
        midboss_pre=_STAGE2_MIDBOSS_PRE,
        boss_pre=_STAGE2_BOSS_PRE,
        boss_post=_STAGE2_BOSS_POST,
    ),
    StageScript(
        index=3,
        title="紅魔館",
        subtitle="Scarlet Devil Mansion  /  Final Stage",
        background=2,
        enemy_small="small3",
        enemy_large="large3",
        waves=_STAGE3_WAVES,
        midboss=None,
        boss=STAGE_BOSS_SPECS["remilia"],
        intro=_STAGE3_INTRO,
        boss_pre=_STAGE3_BOSS_PRE,
        boss_post=_STAGE3_BOSS_POST,
    ),
)
