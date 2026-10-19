"""Сопоставление оплаты с учеником и/или родителем по ФИО, телефону и сумме.

Учитывает то, как банки пишут имена в чеках: «Иван Петрович С.» (имя, отчество,
инициал фамилии), падежи в назначении («за Петрова Сашу»), уменьшительные имена.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

# Распространённые уменьшительные формы → полное имя.
DIMINUTIVES = {
    "саша": "александр", "шура": "александр", "женя": "евгений", "петя": "петр",
    "ваня": "иван", "вова": "владимир", "володя": "владимир", "дима": "дмитрий",
    "миша": "михаил", "коля": "николай", "сережа": "сергей",
    "алеша": "алексей", "леша": "алексей", "андрюша": "андрей", "костя": "константин",
    "паша": "павел", "гоша": "георгий", "егорка": "егор", "тема": "артем",
    "артемка": "артем", "макс": "максим", "кирюша": "кирилл",
    "даня": "даниил", "данила": "даниил", "слава": "вячеслав",
    "витя": "виктор", "толя": "анатолий", "гриша": "григорий", "лева": "лев",
    "маша": "мария", "даша": "дарья", "катя": "екатерина", "настя": "анастасия",
    "наташа": "наталья", "лена": "елена", "оля": "ольга", "таня": "татьяна",
    "юля": "юлия", "аня": "анна", "ира": "ирина", "света": "светлана",
    "соня": "софья", "софия": "софья", "поля": "полина", "лиза": "елизавета",
    "вика": "виктория", "ксюша": "ксения", "варя": "варвара", "люба": "любовь",
    "надя": "надежда", "галя": "галина", "валя": "валентина", "уля": "ульяна",
}

STOP_WORDS = {
    "за", "оплата", "оплату", "перевод", "занятия", "занятие", "обучение", "кружок",
    "секция", "месяц", "октябрь", "ноябрь", "декабрь", "январь", "февраль", "март",
    "апрель", "май", "июнь", "июль", "август", "сентябрь", "октября", "ноября",
    "декабря", "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "руб", "рублей", "от", "для", "ученик", "ученика",
    "ученица", "ученицы", "мама", "папа", "мать", "отец", "сын", "сына", "дочь",
    "дочери", "и", "в", "на", "по", "с", "к", "у",
}


def normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str | None, keep_initials: bool = True) -> list[str]:
    result = []
    for t in normalize(text).split():
        if t.isdigit() or t in STOP_WORDS:
            continue
        if len(t) == 1 and not keep_initials:
            continue
        result.append(_full_name_form(t))
    return result


def _full_name_form(t: str) -> str:
    """«Сашу», «Пети», «Машей» → полное имя, если это уменьшительная форма."""
    for variant in (t, t[:-1] + "а", t[:-1] + "я", t[:-2] + "а", t[:-2] + "я"):
        if variant in DIMINUTIVES:
            return DIMINUTIVES[variant]
    return t


def token_sim(a: str, b: str) -> float:
    """Сходство двух слов с учётом инициалов и падежных окончаний."""
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:
        return 0.9 if a[0] == b[0] else 0.0
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    if common >= max(3, min(len(a), len(b)) - 2):
        return 0.9
    return fuzz.ratio(a, b) / 100


def name_score(person_name: str, text: str | None) -> float:
    """Насколько вероятно, что в тексте упомянут человек с этим ФИО (0..1)."""
    person = tokens(person_name, keep_initials=False)
    found = tokens(text)
    if not person or not found:
        return 0.0
    bests = []
    for p in person:
        best = 0.0
        for t in found:
            best = max(best, token_sim(p, t))
        bests.append(best)
    bests.sort(reverse=True)
    if len(bests) == 1:
        return bests[0] * 0.8
    score = (bests[0] + bests[1]) / 2
    # Совпало только одно слово (например, одно имя) — это слабый сигнал.
    if bests[1] < 0.75:
        score *= 0.6
    return round(score, 3)


def _given_name_mentioned(person_name: str, text: str | None) -> bool:
    """Упомянуто ли имя (не фамилия) человека. ФИО хранится как «Фамилия Имя Отчество»."""
    person = tokens(person_name, keep_initials=False)
    if not person:
        return False
    given = person[1] if len(person) > 1 else person[0]
    return any(token_sim(given, t) >= 0.9 for t in tokens(text, keep_initials=False))


def phone_tail(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-4:] if len(digits) >= 4 else ""


@dataclass
class Candidate:
    student_id: int | None
    parent_id: int | None
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchInput:
    payer_name: str | None = None
    payer_phone: str | None = None
    purpose: str | None = None
    student_name: str | None = None
    amount: float | None = None


def find_candidates(data: MatchInput, students, parents, aliases=()) -> list[Candidate]:
    students = [s for s in students if s.active]
    student_by_id = {s.id: s for s in students}
    mention_text = " ".join(filter(None, [data.student_name, data.purpose]))
    payer_text = data.payer_name or ""
    payer_tail = phone_tail(data.payer_phone)

    # 1. Оценка каждого родителя как плательщика.
    parent_scores: dict[int, tuple[float, list[str]]] = {}
    for p in parents:
        score = name_score(p.full_name, payer_text)
        reasons = [f"плательщик похож на родителя {p.full_name}"] if score >= 0.6 else []
        mention = name_score(p.full_name, mention_text) * 0.85
        if mention > score:
            score = mention
            reasons = [f"в тексте упомянут родитель {p.full_name}"] if score >= 0.6 else []
        if payer_tail and phone_tail(p.phone) == payer_tail:
            score = min(1.0, max(score, 0.7) + 0.15)
            reasons.append("совпали последние цифры телефона")
        parent_scores[p.id] = (score, reasons)

    # 2. Запомненные написания плательщиков — самый надёжный сигнал.
    alias_hits: list[Candidate] = []
    norm_payer = normalize(payer_text)
    for a in aliases:
        if norm_payer and a.alias == norm_payer:
            alias_hits.append(Candidate(a.student_id, a.parent_id, 0.99, ["плательщик уже встречался ранее"]))

    candidates: list[Candidate] = list(alias_hits)

    # 3. Ученики: упоминание в назначении/тексте + совпадение родителя-плательщика.
    for s in students:
        s_score = name_score(s.full_name, mention_text)
        reasons = [f"в тексте упомянут ученик {s.full_name}"] if s_score >= 0.6 else []
        payer_as_student = name_score(s.full_name, payer_text) * 0.9
        if payer_as_student > s_score:
            s_score = payer_as_student
            reasons = [f"плательщик похож на ученика {s.full_name}"] if s_score >= 0.6 else []

        best_parent_id, best_parent_score, parent_reasons = None, 0.0, []
        for p in s.parents:
            ps, pr = parent_scores.get(p.id, (0.0, []))
            if ps > best_parent_score:
                best_parent_id, best_parent_score, parent_reasons = p.id, ps, pr

        # Если у родителя несколько детей, по одному родителю ребёнка не определить.
        siblings = 1
        if best_parent_id is not None:
            parent = next(p for p in s.parents if p.id == best_parent_id)
            siblings = len([c for c in parent.students if c.id in student_by_id])
        via_parent = best_parent_score if siblings == 1 else best_parent_score * 0.75

        score = max(s_score, via_parent)
        # Родитель найден, и в тексте названо имя именно этого ребёнка («за Машу»).
        if best_parent_score >= 0.6 and siblings > 1 and _given_name_mentioned(s.full_name, mention_text):
            score = max(score, best_parent_score)
            reasons.append("в тексте указано имя ребёнка")
        if s_score >= 0.6 and best_parent_score >= 0.6:
            score = min(1.0, score + 0.1)
        if data.amount and s.monthly_fee and abs(data.amount - s.monthly_fee) < 0.01:
            score = min(1.0, score + 0.05)
            reasons.append("сумма совпадает с ежемесячной оплатой")
        if score < 0.3:  # слабые варианты показываем только как подсказки
            continue
        candidates.append(
            Candidate(s.id, best_parent_id if best_parent_score >= 0.5 else None, round(score, 3),
                      reasons + parent_reasons)
        )

    # 4. Родитель без однозначного ребёнка — оплату можно зафиксировать на родителя.
    for p in parents:
        score, reasons = parent_scores[p.id]
        active_children = [c for c in p.students if c.id in student_by_id]
        if score >= 0.3 and len(active_children) != 1:
            candidates.append(Candidate(None, p.id, round(score, 3), reasons))

    # Убираем дубли, оставляя лучший вариант.
    best: dict[tuple, Candidate] = {}
    for c in candidates:
        key = (c.student_id, c.parent_id)
        if key not in best or best[key].score < c.score:
            best[key] = c
    return sorted(best.values(), key=lambda c: c.score, reverse=True)


def _related(a: Candidate, b: Candidate) -> bool:
    """Кандидаты не конкурируют: это тот же ученик или ученик и его же родитель."""
    if a.student_id and a.student_id == b.student_id:
        return True
    if a.parent_id and a.parent_id == b.parent_id and not (a.student_id and b.student_id):
        return True
    return False


def decide(candidates: list[Candidate], threshold: float) -> Candidate | None:
    """Возвращает кандидата, если он достаточно уверенный и однозначный."""
    if not candidates or candidates[0].score < threshold:
        return None
    top = candidates[0]
    for other in candidates[1:]:
        if not _related(top, other) and top.score - other.score < 0.1:
            return None
    if top.student_id is None:
        # Оплата от родителя: если ребёнок тоже уверенно определился — берём ребёнка.
        for other in candidates[1:]:
            if other.student_id and _related(top, other) and top.score - other.score < 0.1:
                return Candidate(other.student_id, top.parent_id, other.score,
                                 top.reasons + other.reasons)
    return top
