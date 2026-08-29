"""Lorebook bootstrap helpers for built-in world templates."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.knowledge.visibility import visibility_values

logger = logging.getLogger("trpg")

# #170 重审计把内置模板条目分成了公开/秘密，但 ensure_world_from_template 对
# 已存在的条目 id 直接跳过——老安装的 SQLite 里还是旧版 GM-secret 正文，
# 重审计的公开常识永远生效不了；新拆出的秘密条目反而会被新增。
# 本清单记录重审计**之前**官方原文全文（world_id -> entry_id -> content）：
# 仅当数据库条目正文与之一字不差（用户从未编辑）且用户未设置过 visible_to 时，
# 才升级为当前模板版本的内容与可见性。用户编辑过的条目绝不触碰；
# 升级完成后正文与清单不再一致，天然幂等。
LEGACY_BUNDLED_CONTENT: dict[str, dict[str, str]] = {
    "coc_horror": {
        "event_fishermen_missing": "过去三个月，阿卡姆港有三艘渔船出海后未归，共7名渔民失踪。唯一回来的渔民精神失常，整日念叨着「绿色的光」和「海底的城市」。当地报纸对此含糊其词，但镇民间私下议论纷纷。",
        "loc_arkham": "位于美国马萨诸塞州东海岸的古老大学城。密斯卡托尼克大学是小镇的心脏，拥有全美最大的神秘学书籍收藏。镇上建筑多为殖民地风格，街道狭窄曲折。当地人对外来者态度警惕但不失礼貌。靠海的一侧有渔港，最近渔民们都不太愿意出海。",
        "loc_fishing_port": "阿卡姆镇东侧的渔港。空气中弥漫着鱼腥和海水的味道。码头上绑着几艘渔船，其中一艘船的船身上有奇怪的抓痕——不像是正常的磨损。港口的灯塔在夜间会自动亮起，但最近灯塔管理员声称看到海面上有「绿色的磷光」。",
        "loc_howard_house": "位于阿卡姆镇东区的一栋二层木制老宅，门牌号榆树街13号。院中草木杂乱，信箱塞满了未取的信件。邻居说最近夜间看到二楼书房的灯会亮起，但白天窗帘紧闭，敲门无人应答。后院有个上了锁的工具棚。",
        "loc_miskatonic": "成立于1690年的古老大学。图书馆的禁书区收藏着《死灵之书》的拉丁文译本残篇、《无名祭祀书》等禁忌典籍，只有持教授签字的许可才能进入。霍华德教授的办公室在考古学系楼的三层，门牌号307。",
        "npc_howard": "密斯卡托尼克大学考古学系教授，45岁。你的远房表亲。半年前带队前往南太平洋波纳佩岛考古发掘，回来后人就变得沉默寡言。最近一个月完全失联——他的办公室被锁，同事说他请了病假。但据他邻居说，夜间偶尔看到他家的窗户亮着灯，窗帘紧闭。"
    },
    "coc_horror_en": {
        "event_missing_fishermen": "Over the past three months, three fishing boats have failed to return to Arkham port, leaving seven fishermen missing. The one fisherman who came back is out of his wits, mumbling day and night about a 'green light' and a 'city under the sea.' The local paper is evasive on the matter, but townsfolk whisper among themselves.",
        "loc_arkham": "An old college town on the eastern coast of Massachusetts. Miskatonic University is its heart, and its library holds the largest collection of occult works in the United States. The town's architecture is largely colonial, with narrow winding streets. Locals treat outsiders with wary courtesy. The seaward side has a fishing port, but lately the fishermen have been reluctant to put out to sea.",
        "loc_arkham_fishing_port": "The fishing port on the east side of Arkham. The air hangs thick with the smell of fish and saltwater. Several fishing boats are tied at the dock, and one of them bears strange scratch marks along its hull, nothing like ordinary wear. The harbor lighthouse lights itself at night, but its keeper now reports seeing a 'green phosphorescence' out on the water.",
        "loc_howard_residence": "A two-story wooden house on the east side of Arkham, 13 Elm Street. The yard is overgrown, and the mailbox is crammed with uncollected letters. Neighbors say a light comes on in the upstairs study at night, but by day the curtains stay drawn and knocking brings no answer. A locked tool shed stands at the back.",
        "loc_miskatonic_university": "Founded in 1690, an ancient university. The library's restricted shelves hold forbidden volumes including fragments of a Latin translation of the Necronomicon and the Unaussprechlichen Kulten. Access requires a pass signed by a professor. Professor Howard's office is on the third floor of the Archaeology building, room 307.",
        "npc_professor_howard": "A professor of archaeology at Miskatonic University, 45 years old. Your distant cousin. Six months ago he led an expedition to the island of Pohnpei in the South Pacific; since returning he has grown withdrawn and taciturn. For the past month he has been entirely out of reach: his office is locked, and colleagues say he is on sick leave. His neighbors, however, report that a light sometimes glows behind his curtains at night, always drawn tight."
    },
    "default_fantasy": {
        "event_forest_disturbance": "最近一个月，黑松林中的动物变得异常凶暴。三周前有两名猎人在林中失踪，上周有一队商人的马车在森林边缘遭到不明生物袭击。冒险者公会悬赏调查此事，赏金50金币。有目击者称看到林中深处有奇怪的光亮。",
        "faction_adventurer_guild": "遍布大陆的冒险者组织。在石桥镇的分会由一名退役冒险者「铁锤」汉克管理。公会提供任务发布、物资补给、情报交换等服务。冒险者等级从铜牌到秘银共6级。新手默认铜牌。",
        "loc_blackpine_forest": "石桥镇北面的一片广袤针叶林。林中光线昏暗，常年雾气弥漫。传闻森林深处有一座废弃的古塔，曾是某位法师的居所。近期林中的动物变得异常凶猛，有猎人在林中失踪。",
        "loc_golden_lion_inn": "冒险者小镇「石桥镇」中心最大的酒馆和旅馆。一楼是吧台和散座大厅，二楼有8间客房（每晚5银币）。公告板上张贴着各种任务和悬赏。酒馆的招牌菜是烤野猪肉和蜂蜜麦酒。",
        "loc_stonebridge": "位于艾泽兰王国北境的中型城镇，人口约2000。镇子因一座古老的石桥得名。主要建筑：金狮酒馆、冒险者公会、铁匠铺、杂货店、神殿。镇北是通往黑松林的官道，镇南通往王都。",
        "npc_blacksmith": "石桥镇唯一的铁匠，矮人血统，脾气火爆但手艺精湛。可以维修和购买武器防具。偶尔会有自己打造的精品装备出售（价格不菲）。对矿石品质很挑剔。",
        "npc_innkeeper": "金狮酒馆的老板，50多岁，秃顶微胖，总是笑呵呵的。在镇上经营酒馆30年，认识三教九流的人，消息灵通但从不主动惹事。对冒险者态度友好，愿意提供一些本地情报。"
    },
    "default_fantasy_en": {
        "event_forest_disturbance": "During the last month, animals from Blackpine Forest have become unusually aggressive. Two hunters vanished three weeks ago, and a merchant wagon was attacked near the tree line last week. Witnesses claim they saw pale blue light deeper in the forest.",
        "faction_adventurers_guild": "A loose network that posts jobs, pays rewards, brokers information, and keeps basic records on adventuring parties. The Stonebridge office is run by Hank Ironhand, a retired delver who distrusts clean boots and vague reports.",
        "loc_blackpine_forest": "A vast conifer forest north of Stonebridge. The air beneath the branches is dim and cold even at noon. Hunters report violent animals, strange lights, and paths that seem to shift after sundown. An abandoned tower is rumored to stand somewhere in the deeper woods.",
        "loc_golden_lion_inn": "The largest inn in Stonebridge, with a common room on the first floor and eight modest rooms upstairs. The adventurers' guild board is mounted beside the hearth. Its best-known dishes are roast boar, onion stew, and honey ale.",
        "loc_stonebridge": "A market town of roughly two thousand people on the northern road. It is named for an ancient stone bridge crossing the mill river. Important places include the Golden Lion Inn, the guild office, a smithy, a shrine, and several supply shops.",
        "npc_old_tom": "The owner of the Golden Lion Inn. He is in his fifties, cheerful, watchful, and careful about the trouble he lets through his door. After thirty years behind the bar, he knows merchants, hunters, guards, and guild agents by name. He is friendly to adventurers and can share local rumors."
    },
    "greymoor": {
        "faction_waykeepers": "维护灰沼引路灯、路标和安全路线的地方组织。他们不是军队，却掌握最可靠的道路记录，也负责在雾季寻找迷路者。",
        "loc_mistbound_road": "一条连接边境聚落的古老高埂路。道路两旁是浅沼和芦苇地，坚实路面很窄；货车离开车辙后很容易陷入泥中。",
        "npc_mira": "年轻的守灯学徒，熟悉灰沼驿道和日常巡灯路线。她认真、直率，在导师失踪后努力维持路灯系统，但缺少独自处理古老魔法异常的经验。",
        "region_greymoor": "王国边缘的低湿边境，遍布芦苇、黑水、泥炭地和零散林丘。晨昏的雾会吞没远处地标，旅行者通常依赖引路灯与守灯人的路线记录。"
    },
    "jp_isekai": {
        "event_monster_activity": "最近三个月，王都周边地区的魔物出现频率增加了约三成。平时只有史莱姆的下水道出现了剧毒变种，北部森林出现了原本栖息在深山的巨狼。公会将此事件的调查等级定为B级，悬赏500金币。有学者认为这可能与某个古代遗迹的封印松动有关。",
        "faction_demon_lord_remnants": "百年前被勇者击败的魔王军残余势力。如今分散在荒野和迷宫中，各自为政。其中最强的四天王残党仍在各自领地活动，但已无力组织大规模进攻。最近半年来，各地魔物活动频率明显升高，有冒险者推测可能有人在暗中统一残党。",
        "loc_guild_hq": "王都中心的一座四层石造建筑。一楼是任务大厅和登记柜台，二楼是餐厅和休息室，三楼是高级冒险者的专属区域，四楼是公会管理办公室。大厅里悬挂着历代S级冒险者的画像。任务板每小时由魔法自动刷新一次。",
        "loc_royal_capital": "人类王国艾尔德兰的首都，人口约五十万。城市以王宫为中心呈放射状布局。主要区域：商业区（装备店、药水铺、魔法道具店）、住宅区、神殿区（治愈神殿、冒险者安息所）、贵族区。城墙上终年有王国骑士团巡逻。",
        "loc_slime_sewer": "王都地下的庞大水道网络。近年由于魔素浓度异常升高，下水道中开始出现魔物——主要是蓝色史莱姆和巨型老鼠。适合新人冒险者练手。有传闻说下水道深处连接着一个古老的迷宫遗迹。",
        "npc_old_warrior": "公会二楼酒馆的常客，六十多岁的退役B级冒险者。年轻时曾跟随勇者队伍讨伐魔王军，现在每天在酒馆里喝酒讲故事。虽然看起来是个普通老头，但偶尔会给出非常精准的战斗建议。据说他还藏着几件传说级的装备没卖。",
        "npc_receptionist": "冒险者公会总部的新人接待员，银发碧眼的少女，总是带着职业微笑。虽然看起来柔弱，但据说曾是A级冒险者。负责为新人冒险者登记和分配任务。对工作认真负责，偶尔会透露一些任务的内幕情报。"
    },
    "jp_isekai_en": {
        "event_monster_activity": "Over the past three months, monster sightings around the royal capital have risen by roughly thirty percent. Poisonous variants have appeared in sewers that previously held only slimes, and giant wolves native to deep mountains have been seen in the northern woods. The guild has rated this investigation B-rank, with a bounty of 500 gold. Some scholars suspect a loosening seal on an ancient ruin may be to blame.",
        "faction_demon_lord_remnants": "Remnants of the Demon Lord's army, defeated by the Hero a century ago. They are now scattered across the wilds and labyrinths, each faction acting on its own. The strongest of them, the Four Heavenly Kings' remnants, still operate in their respective territories but can no longer mount large-scale offensives. Over the past six months, monster activity has clearly risen across the land. Some adventurers suspect someone is secretly reuniting the remnants.",
        "loc_guild_hq": "A four-story stone building at the heart of the royal capital. The first floor houses the quest hall and registration counter; the second floor, a dining hall and lounge; the third floor, an exclusive area for high-ranking adventurers; the fourth floor, the guild's administrative offices. Portraits of past S-rank adventurers line the hall. The quest board refreshes itself by magic once an hour.",
        "loc_royal_capital": "Capital of the human kingdom of Eldran, with a population of roughly half a million. The city is laid out radially around the royal palace. Main districts: the commercial quarter (equipment shops, potion vendors, magical item stores), the residential quarter, the temple quarter (with the Healing Temple and the adventurers' rest hall), and the noble quarter. The city walls are patrolled year-round by the Royal Knight Order.",
        "loc_slime_sewer": "A vast network of waterways beneath the royal capital. In recent years, an abnormal rise in mana concentration has drawn monsters into the sewers: chiefly blue slimes and giant rats. It is a good training ground for novice adventurers. Rumor holds that the sewers' deepest reaches connect to the ruins of an ancient labyrinth.",
        "npc_old_warrior_grey": "A regular at the tavern on the second floor of the guild hall, a retired B-rank adventurer in his sixties. In his youth he rode with the Hero's party against the Demon Lord's army; now he spends his days drinking and telling stories. He looks like an ordinary old man, but from time to time he offers pinpoint combat advice. Rumor has it he still keeps a few pieces of legendary gear he has never sold.",
        "npc_receptionist_lily": "The newcomers' receptionist at Adventurers' Guild headquarters, a silver-haired, blue-eyed girl who never loses her professional smile. Though she looks fragile, rumor says she was once an A-rank adventurer. She registers new adventurers and assigns quests. She takes her work seriously and occasionally lets slip insider details about certain quests."
    },
    "scifi_cyberpunk": {
        "loc_cloud_tower": "新东京市中心一座高达1003米的巨型建筑。下700层是MKG集团的总部和商业设施，上300层是超级富豪的封闭式住宅区。塔内空气由中央净化系统供应，与外界的污染空气隔离。顶部的空中花园只有持有白金通行证的人才能进入。安保是军事级别的。",
        "loc_red_eye_bar": "涉谷地下市场B2层的酒馆。老板是一个装了义眼的前佣兵，对客人不多问。酒馆墙上挂满了各种退役武器和义体零件作为装饰。这里的规矩是：不打架、不窃听、不做生意——要交易去别处。角落里有一个加密通讯终端，投币使用。",
        "loc_shibuya_market": "新东京涉谷区地下的三层非法市场。地面上是光鲜的购物中心，地下则是另外一番景象。这里有贩卖二手义体的黑诊所、走私电子零件的摊位、以及各种不正规的情报贩子。市场入口藏在一家拉面店的后厨。第B2层有一家名为「红眼」的老酒馆，是黑客和佣兵们接头的地点。",
        "npc_market_doctor": "涉谷地下市场最知名的义体医生。经营着一家没有招牌的黑诊所。曾是大企业的义体研发工程师，因为非法实验被开除。赤井的技术和正规医院一样好，但收费只有三分之一。不过他的义体来源不明——有些可能是从尸体上回收的。"
    },
    "scifi_cyberpunk_en": {
        "loc_cloudspire": "A 1,003-meter megastructure at the heart of Neo-Tokyo. The lower 700 floors house MKG headquarters and corporate retail; the upper 300 floors are a sealed residential arcology for the ultra-rich. Air inside is scrubbed by a central purification system, cut off from the smog below. The sky garden at the summit is accessible only with a platinum pass. Security is military-grade.",
        "loc_red_eye_bar": "A bar on level B2 of the Shibuya Underground. The owner is a former merc with a prosthetic eye who never asks questions. The walls are lined with decommissioned weapons and cyberware parts, more trophy than decor. House rules: no fighting, no eavesdropping, no dealing--take your business elsewhere. A coin-operated encrypted comm terminal sits in the corner.",
        "loc_shibuya_market": "Three illegal levels buried beneath Shibuya's shopping district. Up top, the malls gleam; down here, the real business runs--black clinics selling second-hand cyberware, stalls hawking smuggled components, and brokers who deal in information that never appears on a feed. The entrance is hidden behind a ramen shop's kitchen. On level B2 sits an old bar called the Red Eye, where hackers and mercs go to talk business.",
        "npc_dr_akai": "The most reputed ripperdoc in the Shibuya Underground, running an unmarked clinic. Former cyberware R&D engineer at a major corp, fired for unlicensed experiments. Akai's work is as clean as a hospital's, at a third of the price--but the provenance of his implants is questionable. Some are likely harvested from the dead."
    },
    "zhongshi_fantasy": {
        "event_strange_light": "近一个月来，枯木崖顶夜夜出现诡异绿光，持续约一炷香时间。镇民人心惶惶，已有人搬离。青石镇镇长发话：谁能查明真相，赏银百两。有老猎人说那绿光像是「妖丹」的光芒——有妖物在崖下修炼。",
        "faction_kunlun_sword_sect": "西部第一剑道宗门，坐落于昆仑山脉中。以「昆仑十三剑」闻名天下。现任掌门「剑圣」独孤寒，据说是当世仅存的几位分神境高手之一。剑宗弟子行事正派，以降妖除魔为己任。每隔三年开山收徒一次，天下少年皆以拜入剑宗为荣。",
        "loc_kumu_cliff": "青石镇以西三里处的一座陡峭山崖。崖顶有一棵千年枯松，故名枯木崖。崖下有数个天然石洞，据说是古代修士的洞府遗迹。近一个月来，夜间崖顶常出现诡异绿光，有采药人声称看到洞中有妖物出没。",
        "loc_qingshi": "大夏王朝西部边陲的小镇，因镇外青石崖而得名。人口约1500，半农半猎。镇上有茶馆、药铺、铁匠铺和一间小客栈「清风居」。每月逢五有集市，远近山民都会来此交易。镇子虽小，但地处通往昆仑山脉的要道，过往的江湖人士不少。",
        "npc_herbalist": "青石镇的采药老人，六十多岁，在枯木崖一带采药三十余年。三天前在崖下采药时目睹洞中有「人形黑影」闪过，吓得连夜跑回镇子。老王口吃，说话吞吞吐吐，但为人老实不撒谎。",
        "npc_teahouse_owner": "清风茶馆的老板，四十来岁，面容清瘦但双目有神。据说是从京城退隐来此的，来历不明。茶馆是镇上的消息集散地，柳掌柜消息灵通，对江湖事了如指掌，但从不主动透露自己的事。"
    },
    "zhongshi_fantasy_en": {
        "event_deadwood_cliff_strange_light": "For the past month, eerie green light has appeared atop Deadwood Cliff every night, lasting about the time it takes to burn a stick of incense. The townsfolk are in a panic, and some have already moved away. The mayor of Bluestone Town has offered a hundred taels of silver to anyone who can uncover the truth. An old hunter says the green light looks like the glow of a 'demon core'—a monster is cultivating beneath the cliff.",
        "faction_kunlun_sword_sect": "The foremost swordsmanship sect in the west, seated among the Kunlun Mountains. It is renowned across the land for the 'Thirteen Swords of Kunlun.' Its current sect master, Dugu Han, known as the 'Sword Saint,' is said to be one of the few Spirit Split realm masters left in the world. Disciples of the Sword Sect act with righteousness and take slaying demons and evil as their duty. The sect opens its gates to take in new disciples once every three years, and youths across the realm consider it an honor to be accepted.",
        "loc_bluestone_town": "A small town on the western frontier of the Great Xia Dynasty, named for the Bluestone Cliff just outside. Its population of about 1,500 lives by farming and hunting. The town has a teahouse, an apothecary, a smithy, and a small inn called the Clear Breeze Lodge. On every fifth day a market is held, drawing mountain folk from all around to trade. Though small, the town sits on the main road to the Kunlun Mountains, and many wandering figures of the martial world pass through.",
        "loc_deadwood_cliff": "A steep cliff three li west of Bluestone Town. A millennia-old withered pine stands atop it, giving the cliff its name. At its foot lie several natural stone caves, said to be the ruins of an ancient cultivator's dwelling. For the past month, eerie green light has been appearing atop the cliff at night, and a herbalist claims to have seen a monster moving inside the caves.",
        "npc_old_wang_herbalist": "An elderly herbalist of Bluestone Town, in his sixties, who has gathered herbs around Deadwood Cliff for over thirty years. Three days ago, while picking herbs beneath the cliff, he caught sight of a 'human-shaped shadow' flitting through the caves and fled back to town in the dead of night. Old Wang stutters and speaks haltingly, but he is an honest man who does not lie.",
        "npc_shopkeeper_liu": "Owner of the Clear Breeze Teahouse. He is in his forties, thin-faced but with bright, spirited eyes. Word is he retired here from the capital years ago, though his true background remains unknown. The teahouse is the town's hub of news and gossip; Shopkeeper Liu is well-informed and knows the martial world inside out, though he never volunteers anything about himself."
    }
}


def _maybe_upgrade_bundled_entry(lorebook_store: Any, world_id: str, entry_id: str, bundled: dict[str, Any]) -> None:
    """存量正文与重审计前官方原文完全一致（用户从未编辑）时，升级到当前模板版本。"""
    recorded = LEGACY_BUNDLED_CONTENT.get(world_id, {}).get(entry_id)
    if recorded is None:
        return
    existing = lorebook_store.get_entry(entry_id)
    if not existing or existing.get("world_id") != world_id:
        return
    if visibility_values(existing.get("visible_to")):
        return  # 用户设置过可见性，尊重其决定
    if str(existing.get("content") or "") != recorded:
        return  # 正文被用户编辑过，或已经是新版
    lorebook_store.update_entry(entry_id, {
        "content": str(bundled.get("content") or recorded),
        "visible_to": list(bundled.get("visible_to") or []),
    })


def ensure_world_from_template(lorebook_store: Any, world_id: str, template: dict[str, Any]) -> int:
    """Ensure one template world and its starter entries exist in the lorebook DB."""
    if not lorebook_store or not world_id or not template:
        return 0
    template_language = template.get("language", "zh-CN")
    existing_world = lorebook_store.get_world(world_id)
    if not existing_world:
        lorebook_store.create_world(
            world_id,
            template.get("world_name", world_id),
            description=template.get("description", ""),
            language=template_language,
        )
    elif existing_world.get("language") != template_language:
        # Early databases acquired the zh-CN migration default even for English
        # bundled templates. Update metadata in place; never replace user entries.
        lorebook_store.update_world_language(world_id, template_language)

    inserted = 0
    for raw_entry in template.get("starter_lorebook", []):
        if not isinstance(raw_entry, dict) or not raw_entry.get("id"):
            continue
        entry = deepcopy(raw_entry)
        entry["world_id"] = world_id
        entry_id = str(entry["id"])
        existing = lorebook_store.get_entry(entry_id)
        if existing and existing.get("world_id") == world_id:
            _maybe_upgrade_bundled_entry(lorebook_store, world_id, entry_id, entry)
            continue
        if existing and existing.get("world_id") != world_id:
            entry["id"] = f"{world_id}_{entry_id}"
            if lorebook_store.get_entry(entry["id"]):
                continue
        lorebook_store.add_entry(entry)
        inserted += 1
    return inserted


def seed_builtin_worlds(lorebook_store: Any, worlds_dir: Path) -> int:
    """Import bundled starter lorebooks so the lorebook page is useful on first run."""
    if not lorebook_store or not worlds_dir.is_dir():
        return 0
    total = 0
    for path in sorted(worlds_dir.glob("*.json")):
        if path.name.startswith("ai_") or "_copy_" in path.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            world_id = str(data.get("world_id") or path.stem).strip()
            if not world_id or data.get("deprecated") or not data.get("starter_lorebook"):
                continue
            total += ensure_world_from_template(lorebook_store, world_id, data)
        except Exception:
            logger.warning("内置世界书初始化失败: %s", path, exc_info=True)
    if total:
        logger.info("已初始化内置世界书条目: %d", total)
    return total
