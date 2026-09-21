"""Lorebook 关键词匹配器 —— 在纯文本中匹配世界书条目关键词，支持递归触发、AND/NOT逻辑、常量条目、概率、分组、正则。"""

from __future__ import annotations

import json
import logging
import random
import re
from collections import deque
from typing import Callable

from src.lorebook.activation import evaluate_probability

logger = logging.getLogger("trpg")

MAX_RECURSIVE_DEPTH = 3
MIN_FUZZY_KEY_LEN = 2       # 最短模糊匹配关键词长度


class KeywordMatcher:
    """关键词匹配器，支持精确匹配 + 模糊子串回退 + AND逻辑 + 常量条目。"""

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

    def match(self, text: str) -> list[dict]:
        """匹配文本中出现的所有关键词。常量条目始终包含。"""
        matched_ids = self._candidate_ids(text)
        if not matched_ids:
            matched_ids.update(self._fuzzy_match(text))
        matched_ids.update(self._get_constant_ids())
        matched_ids = self._apply_match_mode(matched_ids, text)
        # 概率过滤
        matched_ids = self._apply_probability(matched_ids)
        # 分组竞争
        matched_ids = self._apply_group_competition(matched_ids)
        return self._sort_by_tier(matched_ids)

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

    @classmethod
    def _logic(cls, entry: dict) -> str:
        mode = str(entry.get("match_mode", entry.get("selective_logic", "any")) or "any").lower()
        return {"0": "any", "1": "all", "2": "not_all", "3": "not_any", "and": "all", "or": "any"}.get(mode, mode)

    @classmethod
    def _entry_matches(cls, entry: dict, text: str) -> bool:
        primary = cls._keys(entry, "keywords")
        secondary = cls._keys(entry, "secondary_keys")
        mode = cls._logic(entry)
        if not primary and not secondary:
            return False
        primary_hits = [cls._match_keyword(key, text, entry) for key in primary]
        secondary_hits = [cls._match_keyword(key, text, entry) for key in secondary]
        if mode == "all":
            return all(primary_hits or [False]) and (all(secondary_hits) if secondary else True)
        if mode == "not_any":
            return not any(primary_hits + secondary_hits)
        if mode == "not_all":
            checks = primary_hits + secondary_hits
            return not checks or not all(checks)
        # ST-style selective keys: primary activation is required when secondary
        # keys are configured; secondary keys are an additional any-match gate.
        return any(primary_hits) and (any(secondary_hits) if secondary else True)

    def _candidate_ids(self, text: str) -> set[str]:
        return {
            eid for eid, entry in self._entries.items()
            if self._logic(entry) in ("not_any", "not_all") or self._entry_matches(entry, text)
        }

    def _apply_match_mode(self, matched_ids: set[str], text: str) -> set[str]:
        """逻辑过滤：AND（所有关键词须出现）/ NOT（关键词不出现才激活）。"""
        result = set(matched_ids)
        for eid in list(result):
            entry = self._entries.get(eid)
            if not entry:
                result.discard(eid)
                continue
            mode = self._logic(entry)
            if mode == "any":
                continue
            keywords = self._keys(entry, "keywords") + self._keys(entry, "secondary_keys")
            if not keywords:
                result.discard(eid)
                continue
            if not self._entry_matches(entry, text):
                result.discard(eid)
        return result

    def _apply_probability(self, matched_ids: set[str]) -> set[str]:
        """概率过滤：probability < 100 的条目按概率激活。"""
        result = set(matched_ids)
        for eid in list(result):
            entry = self._entries.get(eid)
            if not entry:
                result.discard(eid)
                continue
            prob = int(entry.get("probability", 100))
            accepted, _trace = evaluate_probability(entry, rng=self._rng or random.random)
            if not accepted:
                result.discard(eid)
                logger.debug("概率过滤: %s (probability=%d) 未激活",
                            entry.get("name", eid), prob)
        return result

    def _apply_group_competition(self, matched_ids: set[str]) -> set[str]:
        """分组竞争：同 group 的条目仅保留 group_weight 最高的。"""
        groups_by_name: dict[str, list[tuple[str, int]]] = {}
        for eid in matched_ids:
            entry = self._entries.get(eid)
            if not entry:
                continue
            group_names = self._keys(entry, "groups")
            group = str(entry.get("group", "") or "").strip()
            if group:
                group_names.append(group)
            if not group_names or str(entry.get("group_scoring", "") or "").lower() in {"all", "allow_all"}:
                continue
            weight = int(entry.get("group_weight", 1))
            for group_name in set(group_names):
                groups_by_name.setdefault(group_name, []).append((eid, weight))
        removed: set[str] = set()
        for group, members in groups_by_name.items():
            if len(members) <= 1:
                continue
            members.sort(key=lambda x: (
                -x[1],
                -int(self._entries.get(x[0], {}).get("priority", 0) or 0),
                int(self._entries.get(x[0], {}).get("order", 100) or 100),
                x[0],
            ))
            if any("prioritize_inclusion" in self._entries.get(eid, {}) for eid, _ in members):
                prioritized = [item for item in members if bool(self._entries.get(item[0], {}).get("prioritize_inclusion", False))]
                if prioritized:
                    prioritized.sort(key=lambda x: (-int(self._entries.get(x[0], {}).get("priority", 0) or 0), int(self._entries.get(x[0], {}).get("order", 100) or 100), x[0]))
                    winner = prioritized[0][0]
                else:
                    total = sum(max(1, weight) for _, weight in members)
                    roll = (self._rng or random.random)() * total
                    winner = members[-1][0]
                    for eid, weight in members:
                        roll -= max(1, weight)
                        if roll < 0:
                            winner = eid
                            break
            else:
                winner = members[0][0]
            # ``members`` is sorted for winner selection, but the winner may
            # be a prioritized entry that was not first in the original set.
            # Remove by identity so the selected winner is always retained.
            for eid, _ in members:
                if eid != winner:
                    removed.add(eid)
            logger.debug("分组竞争: group=%s winner=%s removed=%d",
                        group, self._entries.get(winner, {}).get("name", winner),
                        len(members) - 1)
        return matched_ids - removed

    def _get_constant_ids(self) -> set[str]:
        return {eid for eid, entry in self._entries.items() if entry.get("is_constant")}

    def _fuzzy_match(self, text: str) -> set[str]:
        def fuzzy_keyword_hit(keyword: str, entry: dict) -> bool:
            # Fuzzy matching is only a fallback for plain keyword entries.  It
            # must still honor entry-level case semantics; otherwise a fuzzy
            # fallback could bypass a case-sensitive secondary-key gate.
            if entry.get("use_regex") or entry.get("match_whole_words") or str(keyword).startswith("/"):
                return False
            if entry.get("case_sensitive", False):
                return False
            needle = keyword.casefold()
            haystack = text.casefold()
            return any(needle[i:i + 2] in haystack for i in range(len(needle) - 1))

        matched: set[str] = set()
        for eid, entry in self._entries.items():
            if not bool(entry.get("_lorebook_fuzzy_enabled", True)):
                continue
            primary = self._keys(entry, "keywords")
            secondary = self._keys(entry, "secondary_keys")
            mode = self._logic(entry)
            if not primary and not secondary:
                continue
            primary_hits = [self._match_keyword(key, text, entry) or fuzzy_keyword_hit(key, entry) for key in primary]
            secondary_hits = [self._match_keyword(key, text, entry) or fuzzy_keyword_hit(key, entry) for key in secondary]
            if mode == "all":
                active = all(primary_hits or [False]) and (all(secondary_hits) if secondary else True)
            elif mode == "not_any":
                active = not any(primary_hits + secondary_hits)
            elif mode == "not_all":
                checks = primary_hits + secondary_hits
                active = not checks or not all(checks)
            else:
                active = any(primary_hits) and (any(secondary_hits) if secondary else True)
            if active:
                matched.add(eid)
        return matched

    def match_with_recursive(self, text: str, timed_state: dict[str, dict] | None = None) -> list[dict]:
        if not text or not self._index:
            sticky_ids = self._get_sticky_active_ids(timed_state)
            return self._sort_by_tier(sticky_ids | self._get_constant_ids())

        initial_ids: set[str] = set()

        # 时间效应：sticky 条目 active 时始终激活
        sticky_ids = self._get_sticky_active_ids(timed_state)
        initial_ids.update(sticky_ids)

        # 时间效应：cooldown/delay 活跃期间过滤掉对应条目的关键词
        filtered_ids = self._get_timed_blocked_ids(timed_state)

        initial_ids.update(
            eid for eid in (self._candidate_ids(text) - filtered_ids)
            if not bool(self._entries.get(eid, {}).get("delay_until_recursion", False))
        )
        initial_ids = self._apply_match_mode(initial_ids, text)
        if not initial_ids:
            initial_ids.update(self._fuzzy_match(text) - filtered_ids)
        initial_ids.update(self._get_constant_ids())

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque((eid, 0) for eid in initial_ids)
        while queue:
            eid, depth = queue.popleft()
            if eid in visited or depth >= MAX_RECURSIVE_DEPTH:
                continue
            entry = self._entries.get(eid)
            if not entry or not bool(entry.get("enabled", True)):
                continue
            if depth > 0 and bool(entry.get("non_recursable", False)):
                continue
            visited.add(eid)
            # non_recursable only controls whether this entry may be reached
            # through a recursive pass; a directly matched entry may still
            # propagate its content.  Only prevent_further_recursion stops
            # propagation after the entry has been activated.
            if bool(entry.get("prevent_further_recursion", False)):
                continue
            child_text = str(entry.get("content", "") or "")
            if child_text and bool(entry.get("_lorebook_recursive_scanning", True)):
                child_ids = self._candidate_ids(child_text)
                child_ids = self._apply_match_mode(child_ids, child_text)
                for cid in child_ids - filtered_ids - visited:
                    child = self._entries.get(cid)
                    if child and self._eligible_recursive(child, depth + 1):
                        queue.append((cid, depth + 1))
            triggers = entry.get("triggers_recursive", [])
            if isinstance(triggers, str):
                try:
                    triggers = json.loads(triggers)
                except (json.JSONDecodeError, TypeError):
                    triggers = []
            for tid in triggers if isinstance(triggers, (list, tuple, set)) else []:
                if tid not in visited and tid not in filtered_ids and self._entries.get(tid):
                    child = self._entries[tid]
                    if self._eligible_recursive(child, depth + 1):
                        queue.append((tid, depth + 1))

        # 更新 timed_state：新匹配到的条目若含 sticky/cooldown/delay 则记录
        if timed_state is not None:
            self._apply_time_effects(visited, timed_state)

        # 概率过滤
        visited = self._apply_probability(visited)
        # 分组竞争
        visited = self._apply_group_competition(visited)

        return self._sort_by_tier(visited)

    @staticmethod
    def _eligible_recursive(entry: dict, depth: int) -> bool:
        if bool(entry.get("non_recursable", False)):
            return False
        configured = int(entry.get("scan_depth", 0) or 0)
        if configured > 0 and depth > configured:
            return False
        level = int(entry.get("recursion_level", 0) or 0)
        return level <= 0 or depth >= level

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
        """匹配到条目后，检查其 sticky/cooldown/delay 并更新 timed_state。"""
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
