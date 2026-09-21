"""Lorebook 关键词匹配器 —— 统一 activation eligibility pipeline。

所有候选（lexical / fuzzy / semantic-only）都必须汇入同一个 eligibility pipeline：

    candidate scan
    → primary / secondary / regex / case / whole-word
    → enabled
    → timed gate (cooldown / delay)
    → visibility (fail closed, before recursion)
    → probability
    → inclusion-group competition
    → entry 真正 activated
    → activated entry 才允许写 timed activation state
    → activated entry content 才允许进入 recursion buffer
    → recursive candidates 再走同一 pipeline
    → budget / final ordering (由调用方负责)

因此被 probability 拒绝或 group 竞争落选的条目不会递归、也不会写 sticky /
cooldown / delay；不可见条目更不会通过 recursion 影响其它可见条目。
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Callable

from src.lorebook.activation import (
    evaluate_probability,
    matched_key_score,
    normalize_primary_match_mode,
    normalize_selective_logic,
)

logger = logging.getLogger("trpg")

MAX_RECURSIVE_DEPTH = 3
MIN_FUZZY_KEY_LEN = 2       # 最短模糊匹配关键词长度

# ``group_scoring`` 的确定性词汇：其余值一律按「默认竞争」处理。
_GROUP_ALLOW_ALL = frozenset({"all", "allow_all"})
_GROUP_SCORING_ON = frozenset({"score", "matched_keys", "matched", "use_group_scoring"})


class KeywordMatcher:
    """关键词匹配器，支持精确匹配 + 模糊子串回退 + 逻辑门 + 概率 + 分组竞争。"""

    def __init__(self, *, rng: Callable[[], float] | None = None):
        self._index: dict[str, set[str]] = {}
        self._entries: dict[str, dict] = {}
        self._fuzzy_keys: list[str] = []
        self._rng = rng

    def build(self, entries: list[dict]) -> None:
        """从条目列表构建索引。每个条目的 keywords 字段为 JSON 数组。"""
        self._index.clear()
        self._entries.clear()
        self._fuzzy_keys.clear()
        for entry in entries:
            eid = entry["id"]
            self._entries[eid] = entry
            keywords = self._keys(entry, "keywords") + self._keys(entry, "secondary_keys")
            for kw in keywords:
                kw = kw.strip()
                if kw:
                    self._index.setdefault(kw, set()).add(eid)
                    if len(kw) >= MIN_FUZZY_KEY_LEN and kw not in self._fuzzy_keys:
                        self._fuzzy_keys.append(kw)
        logger.info("关键词索引已构建: %d 关键词, %d 条目, %d 模糊键, %d 常量",
                     len(self._index), len(self._entries), len(self._fuzzy_keys),
                     len(self._get_constant_ids()))

    def match(self, text: str, *, is_visible: Callable[[dict], bool] | None = None) -> list[dict]:
        """匹配文本中出现的所有关键词（无递归）。常量条目始终包含。"""
        return self._activate(
            text, timed_state=None, is_visible=is_visible,
            is_candidate=None, extra_candidates=None,
        )

    def match_with_recursive(
        self,
        text: str,
        timed_state: dict[str, dict] | None = None,
        *,
        is_visible: Callable[[dict], bool] | None = None,
        is_candidate: Callable[[dict], bool] | None = None,
        extra_candidates: object = None,
    ) -> list[dict]:
        """统一 activation pipeline（含递归）。

        ``is_visible`` 必须在 recursion 之前生效：不可见条目不得成为结果、不得
        参与递归、也不得写 timed state。``is_candidate`` 只限制本通道的候选发现
        （例如 vector_only 条目不能被关键词通道发现），不影响安全边界。
        ``extra_candidates`` 是其它候选来源（如 semantic 检索）发现的 entry id，
        它们必须走同一套 eligibility。
        """

        return self._activate(
            text, timed_state=timed_state, is_visible=is_visible,
            is_candidate=is_candidate, extra_candidates=extra_candidates,
        )

    # ---- 统一 pipeline ------------------------------------------------------

    def _activate(
        self,
        text: str,
        *,
        timed_state: dict[str, dict] | None,
        is_visible: Callable[[dict], bool] | None,
        is_candidate: Callable[[dict], bool] | None,
        extra_candidates: object,
    ) -> list[dict]:
        visible = is_visible if is_visible is not None else (lambda entry: True)
        discover = is_candidate if is_candidate is not None else (lambda entry: True)
        blocked = self._get_timed_blocked_ids(timed_state)
        sticky = self._get_sticky_active_ids(timed_state)

        semantic_seeds = {str(cid) for cid in (extra_candidates or ())} & set(self._entries)
        # lexical_seeds 只记录 keyword 通道（含 sticky / constant）发现的条目，
        # 用于把 timed activation state 的写入权保留给 keyword authority。
        lexical_seeds: set[str] = set()
        if text and self._index:
            lexical = {
                eid for eid in self._candidate_ids(text)
                if discover(self._entries[eid])
            } - blocked
            if not lexical:
                lexical = {
                    eid for eid in self._fuzzy_match(text)
                    if discover(self._entries[eid])
                } - blocked
            lexical_seeds |= lexical
        lexical_seeds |= sticky | self._get_constant_ids()
        seeds = (semantic_seeds | lexical_seeds) - blocked

        activated: set[str] = set()
        evaluated: set[str] = set()
        probability_cache: dict[str, bool] = {}
        group_decided: dict[str, str] = {}
        # frontier: entry id -> 该条目被发现的文本（供 group scoring 使用）。
        frontier: dict[str, str] = {eid: text for eid in sorted(seeds)}
        depth = 0

        while frontier and depth < MAX_RECURSIVE_DEPTH:
            batch: dict[str, str] = {}
            for eid in sorted(frontier):
                entry = self._entries.get(eid)
                if entry is None or eid in evaluated:
                    continue
                evaluated.add(eid)
                if not self._eligibility_ok(entry, depth=depth, visible=visible):
                    continue
                if not self._probability_ok(eid, entry, probability_cache):
                    continue
                batch[eid] = frontier[eid]
            winners = self._group_winners(batch, group_decided)
            activated |= winners
            frontier = {}
            for eid in sorted(winners):
                frontier.update(self._children_of(eid, excluded=evaluated | activated))
            depth += 1

        # 只有真正 activated 的条目才允许写 timed activation state，且写入权保留给
        # keyword authority：纯 semantic 命中只参与召回，不写 sticky/cooldown/delay。
        if timed_state is not None:
            self._apply_time_effects(activated & lexical_seeds, timed_state)
        return self._sort_by_tier(activated)

    def _eligibility_ok(self, entry: dict, *, depth: int, visible: Callable[[dict], bool]) -> bool:
        """enabled + visibility + timed/recursion eligibility，fail closed。"""

        if not bool(entry.get("enabled", True)):
            return False
        if not visible(entry):
            return False
        recursive_pass = depth > 0
        if bool(entry.get("delay_until_recursion", False)) and not recursive_pass:
            return False
        if recursive_pass:
            # non_recursable 只限制"通过递归被到达"；直接命中的条目仍可传播。
            if bool(entry.get("non_recursable", False)):
                return False
            level = int(entry.get("recursion_level", 0) or 0)
            if level > 0 and depth < level:
                return False
            configured = int(entry.get("scan_depth", 0) or 0)
            if configured > 0 and depth > configured:
                return False
        return True

    def _probability_ok(self, eid: str, entry: dict, cache: dict[str, bool]) -> bool:
        """概率判定每轮每条目只 roll 一次；被拒者不递归、不写 timed state。"""

        if eid not in cache:
            accepted, _trace = evaluate_probability(entry, rng=self._rng or random.random)
            cache[eid] = bool(accepted)
            if not accepted:
                logger.debug("概率过滤: %s (probability=%s) 未激活",
                             entry.get("name", eid), entry.get("probability", 100))
        return cache[eid]

    def _children_of(self, eid: str, *, excluded: set[str]) -> dict[str, str]:
        """activated entry 的内容才允许进入 recursion buffer。"""

        entry = self._entries.get(eid)
        if entry is None or bool(entry.get("prevent_further_recursion", False)):
            return {}
        children: dict[str, str] = {}
        child_text = str(entry.get("content", "") or "")
        if child_text and bool(entry.get("_lorebook_recursive_scanning", True)):
            for cid in sorted(self._candidate_ids(child_text)):
                if cid not in excluded:
                    children[cid] = child_text
        triggers = entry.get("triggers_recursive", [])
        if isinstance(triggers, str):
            try:
                triggers = json.loads(triggers)
            except (json.JSONDecodeError, TypeError):
                triggers = []
        for tid in triggers if isinstance(triggers, (list, tuple, set)) else []:
            tid = str(tid)
            if tid not in excluded and tid in self._entries:
                children[tid] = child_text
        return children

    # ---- 关键词语义 ---------------------------------------------------------

    @staticmethod
    def _keys(entry: dict, field: str) -> list[str]:
        value = entry.get(field, [])
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                value = [value]
        return [str(item).strip() for item in value or [] if str(item).strip()] if isinstance(value, (list, tuple, set)) else []

    @classmethod
    def _match_keyword(cls, keyword: str, text: str, entry: dict | None = None) -> bool:
        """Match a key with entry-level case, whole-word and regex settings."""
        entry = entry or {}
        case_sensitive = bool(entry.get("case_sensitive", False))
        whole_word = bool(entry.get("match_whole_words", False))
        use_regex = bool(entry.get("use_regex", False))
        pattern = keyword
        if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            use_regex = True
            pattern = pattern[1:-1]
        flags = 0 if case_sensitive else re.IGNORECASE
        if whole_word and not use_regex:
            pattern = rf"(?<!\w){re.escape(pattern)}(?!\w)"
            use_regex = True
        if use_regex:
            try:
                return bool(re.search(pattern, text, flags))
            except re.error:
                return False
        return pattern in text if case_sensitive else pattern.casefold() in text.casefold()

    @staticmethod
    def _fuzzy_hit(keyword: str, entry: dict, text: str) -> bool:
        """Fuzzy matching is only a fallback for plain, case-insensitive keys."""

        if entry.get("use_regex") or entry.get("match_whole_words") or str(keyword).startswith("/"):
            return False
        if entry.get("case_sensitive", False):
            return False
        needle = keyword.casefold()
        haystack = text.casefold()
        return any(needle[i:i + 2] in haystack for i in range(len(needle) - 1))

    @staticmethod
    def _primary_mode(entry: dict) -> str:
        """Legacy DiceFrame primary ``match_mode`` (separate from ST logic)."""

        return normalize_primary_match_mode(entry.get("match_mode", "any"))

    @staticmethod
    def _selective_logic(entry: dict) -> str:
        """SillyTavern secondary-key logic: an additional filter, never a primary match."""

        return normalize_selective_logic(entry.get("selective_logic"))

    @classmethod
    def _keyword_decision(cls, entry: dict, text: str, *, fuzzy: bool = False) -> dict[str, Any]:
        """Primary + secondary keyword semantics for one entry — single authority.

        ``_entry_matches`` and the ActivationTrace both read this, so the trace
        can never report a reason that the activation path did not compute.
        """

        primary_keys = cls._keys(entry, "keywords")
        secondary_keys = cls._keys(entry, "secondary_keys")
        mode = cls._primary_mode(entry)
        logic = cls._selective_logic(entry)
        if not primary_keys and not secondary_keys:
            return {"matched": False, "primary_ok": False, "secondary_ok": None,
                    "matched_keys": [], "secondary_matches": [],
                    "mode": mode, "logic": logic}
        # Fuzzy matching is a book/entry-scoped fallback, so it stays opt-out.
        fuzzy = fuzzy and bool(entry.get("_lorebook_fuzzy_enabled", True))
        primary_hits = [
            cls._match_keyword(key, text, entry) or (fuzzy and cls._fuzzy_hit(key, entry, text))
            for key in primary_keys
        ]
        if mode == "all":
            primary_ok = bool(primary_keys) and all(primary_hits)
        elif mode == "not_any":
            primary_ok = not any(primary_hits)
        elif mode == "not_all":
            primary_ok = not (bool(primary_keys) and all(primary_hits))
        else:
            primary_ok = any(primary_hits)
        secondary_ok: bool | None = None
        secondary_hits = [False] * len(secondary_keys)
        if primary_ok and secondary_keys:
            # ST Optional Filter: primary already matched, secondary is a filter.
            secondary_hits = [
                cls._match_keyword(key, text, entry) or (fuzzy and cls._fuzzy_hit(key, entry, text))
                for key in secondary_keys
            ]
            if logic == "and_all":
                secondary_ok = all(secondary_hits)
            elif logic == "not_any":
                secondary_ok = not any(secondary_hits)
            elif logic == "not_all":
                secondary_ok = not all(secondary_hits)
            else:
                secondary_ok = any(secondary_hits)
        matched = bool(primary_ok) and (secondary_ok is not False)
        return {
            "matched": matched,
            "primary_ok": bool(primary_ok),
            "secondary_ok": secondary_ok,
            "matched_keys": [k for k, hit in zip(primary_keys, primary_hits) if hit],
            "secondary_matches": [k for k, hit in zip(secondary_keys, secondary_hits) if hit],
            "mode": mode,
            "logic": logic,
        }

    @classmethod
    def _entry_matches(cls, entry: dict, text: str, *, fuzzy: bool = False) -> bool:
        """Primary semantics + ST selective secondary semantics.

        The primary key must match first. Secondary keys are only an additional
        gate, so a NOT_ANY / NOT_ALL secondary logic can never rescue an entry
        whose primary key did not hit (and can never negate the primary hit).
        """

        return cls._keyword_decision(entry, text, fuzzy=fuzzy)["matched"]

    def keyword_decision(self, entry: dict, text: str) -> dict[str, Any]:
        """Public read-only view of the keyword-channel decision (for ActivationTrace).

        Diagnostics must reuse the activation authority instead of recomputing
        keyword semantics, otherwise the trace can report a different reason.
        """

        return self._keyword_decision(entry, text)

    def _candidate_ids(self, text: str, *, fuzzy: bool = False) -> set[str]:
        return {
            eid for eid, entry in self._entries.items()
            if self._entry_matches(entry, text, fuzzy=fuzzy)
        }

    def _fuzzy_match(self, text: str) -> set[str]:
        return self._candidate_ids(text, fuzzy=True)

    # ---- 分组竞争 -----------------------------------------------------------

    @classmethod
    def _group_names(cls, entry: dict) -> list[str]:
        names = list(cls._keys(entry, "groups"))
        single = str(entry.get("group", "") or "").strip()
        if single:
            names.append(single)
        return list(dict.fromkeys(names))

    @staticmethod
    def _group_allow_all(entry: dict) -> bool:
        return str(entry.get("group_scoring", "") or "").strip().lower() in _GROUP_ALLOW_ALL

    @staticmethod
    def _group_scoring_on(entry: dict) -> bool:
        return str(entry.get("group_scoring", "") or "").strip().lower() in _GROUP_SCORING_ON

    def _score_of(self, eid: str, text: str) -> int:
        entry = self._entries.get(eid, {})
        primary = self._keys(entry, "keywords")
        secondary = self._keys(entry, "secondary_keys")
        return matched_key_score(
            entry,
            primary_hits=[self._match_keyword(key, text, entry) for key in primary],
            secondary_hits=[self._match_keyword(key, text, entry) for key in secondary],
        )

    def _group_winners(self, batch: dict[str, str], decided: dict[str, str]) -> set[str]:
        """Inclusion-group competition：loser 不算 activated、不递归、不写 timed state。

        ``batch`` 是本 pass 已通过普通 eligibility 的候选；``decided`` 记录早前
        pass 已决出 winner 的分组，后到的成员一律落选。
        """

        groups: dict[str, list[str]] = {}
        for eid in batch:
            for name in self._group_names(self._entries.get(eid, {})):
                groups.setdefault(name, []).append(eid)

        winners = set(batch)
        for name, members in groups.items():
            if len(members) <= 1 or any(self._group_allow_all(self._entries.get(m, {})) for m in members):
                continue
            if name in decided:
                winners -= {m for m in members if m != decided[name]}
                continue
            pool = list(members)
            if any(self._group_scoring_on(self._entries.get(m, {})) for m in members):
                best = max(self._score_of(m, batch[m]) for m in members)
                pool = [m for m in members if self._score_of(m, batch[m]) == best]
            prioritized = [
                m for m in pool
                if bool(self._entries.get(m, {}).get("prioritize_inclusion", False))
            ]
            if prioritized:
                # SillyTavern Prioritize Inclusion 依赖较高的 insertion order，
                # 因此 order 必须降序，绝不能写成 ascending。
                prioritized.sort(key=lambda m: (
                    -int(self._entries.get(m, {}).get("priority", 0) or 0),
                    -int(self._entries.get(m, {}).get("order", 100) or 100),
                    str(m),
                ))
                winner = prioritized[0]
            else:
                winner = self._weighted_pick(sorted(pool))
            decided[name] = winner
            winners -= {m for m in members if m != winner}
            logger.debug("分组竞争: group=%s winner=%s removed=%d",
                         name, self._entries.get(winner, {}).get("name", winner),
                         len(members) - 1)
        return winners

    def _weighted_pick(self, pool: list[str]) -> str:
        """group_weight weighted random，RNG 可注入以保证确定性。"""

        if not pool:
            return ""
        if len(pool) == 1:
            return pool[0]
        weights = {m: max(1, int(self._entries.get(m, {}).get("group_weight", 1) or 1)) for m in pool}
        roll = (self._rng or random.random)() * sum(weights.values())
        for eid in pool:
            roll -= weights[eid]
            if roll < 0:
                return eid
        return pool[-1]

    # ---- timed state --------------------------------------------------------

    def _get_constant_ids(self) -> set[str]:
        return {eid for eid, entry in self._entries.items() if entry.get("is_constant")}

    @staticmethod
    def _get_sticky_active_ids(timed_state: dict[str, dict] | None) -> set[str]:
        """获取当前处于 active 状态的 sticky 条目。"""
        if not timed_state:
            return set()
        return {
            eid for eid, state in timed_state.items()
            if (state.get("status") == "active" and state.get("remaining", 0) > 0)
            or state.get("sticky_remaining", 0) > 0
        }

    @staticmethod
    def _get_timed_blocked_ids(timed_state: dict[str, dict] | None) -> set[str]:
        """获取当前被 cooldown 或 delay 阻止的条目 ID。"""
        if not timed_state:
            return set()
        return {
            eid for eid, state in timed_state.items()
            if (state.get("status") in ("cooldown", "delayed") and state.get("remaining", 0) > 0)
            or state.get("cooldown_remaining", 0) > 0
            or state.get("delay_remaining", 0) > 0
        }

    def _apply_time_effects(self, matched_ids: set[str], timed_state: dict[str, dict]) -> None:
        """activated 条目才写 sticky/cooldown/delay（独立计数器）。"""
        for eid in matched_ids:
            entry = self._entries.get(eid)
            if not entry:
                continue
            sticky = int(entry.get("sticky", 0))
            cooldown = int(entry.get("cooldown", 0))
            delay = int(entry.get("delay", 0))
            if sticky <= 0 and cooldown <= 0 and delay <= 0:
                continue

            state = timed_state.setdefault(eid, {})
            if sticky > 0 and state.get("sticky_remaining", 0) <= 0:
                state["sticky_remaining"] = sticky
                logger.debug("世界书 sticky 激活: %s (duration=%d)", entry.get("name", eid), sticky)
            if cooldown > 0 and state.get("cooldown_remaining", 0) <= 0:
                state["cooldown_remaining"] = cooldown
                logger.debug("世界书 cooldown 开始: %s (duration=%d)", entry.get("name", eid), cooldown)
            if delay > 0 and state.get("delay_remaining", 0) <= 0:
                state["delay_remaining"] = delay
                logger.debug("世界书 delay 开始: %s (duration=%d)", entry.get("name", eid), delay)
            # Do not emit the legacy status/remaining shape.  Legacy input is
            # still read by the compatibility predicates above, while all
            # newly-mutated runtime state uses independent counters.

    def _sort_by_tier(self, entry_ids: set[str]) -> list[dict]:
        result = []
        for eid in entry_ids:
            if eid in self._entries:
                result.append(dict(self._entries[eid]))
        tier_order = {"core": 0, "background": 1, "archived": 2}
        result.sort(key=lambda e: (tier_order.get(e.get("tier", "background"), 1),
                                    int(e.get("order", 100))))
        return result

    def reload(self, entries: list[dict]) -> None:
        """重新构建索引（世界书更新后调用）。"""
        self.build(entries)
