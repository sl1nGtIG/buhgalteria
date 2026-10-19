from types import SimpleNamespace as NS

from app.matcher import MatchInput, decide, find_candidates, name_score


def people():
    ivan = NS(id=1, full_name="Сидоров Иван Петрович", phone="+7 912 555-12-34", students=[])
    olga = NS(id=2, full_name="Кузнецова Ольга Викторовна", phone=None, students=[])
    sasha = NS(id=10, full_name="Сидоров Александр", active=True, monthly_fee=5000, parents=[ivan])
    masha = NS(id=11, full_name="Кузнецова Мария", active=True, monthly_fee=4000, parents=[olga])
    petya = NS(id=12, full_name="Кузнецов Пётр", active=True, monthly_fee=4000, parents=[olga])
    ivan.students = [sasha]
    olga.students = [masha, petya]
    return [sasha, masha, petya], [ivan, olga]


def match(**kw):
    students, parents = people()
    return find_candidates(MatchInput(**kw), students, parents)


def test_bank_style_name_matches_parent():
    assert name_score("Сидоров Иван Петрович", "Иван Петрович С.") > 0.85


def test_declined_name_and_diminutive():
    assert name_score("Сидоров Александр", "оплата за Сидорова Сашу") > 0.85


def test_unrelated_name_scores_low():
    assert name_score("Сидоров Иван Петрович", "Ольга Викторовна К.") < 0.5


def test_parent_with_one_child_assigns_child():
    best = decide(match(payer_name="Иван Петрович С.", amount=5000), 0.85)
    assert best and best.student_id == 10 and best.parent_id == 1


def test_parent_with_two_children_assigns_parent_only():
    best = decide(match(payer_name="Ольга Викторовна К.", amount=8000), 0.85)
    assert best and best.student_id is None and best.parent_id == 2


def test_parent_with_two_children_and_child_in_purpose():
    best = decide(match(payer_name="Ольга Викторовна К.", purpose="за Машу", amount=4000), 0.85)
    assert best and best.student_id == 11 and best.parent_id == 2


def test_free_text_with_student_name():
    best = decide(match(purpose="Кузнецов Петя за октябрь"), 0.85)
    assert best and best.student_id == 12


def test_phone_tail_helps():
    cands = match(payer_name="Клиент Сбербанка", payer_phone="+7 (912) ***-12-34")
    assert cands and cands[0].parent_id == 1


def test_unknown_payer_is_not_decided():
    assert decide(match(payer_name="Пупкин Василий"), 0.85) is None
