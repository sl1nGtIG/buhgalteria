from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Parent, Student
from ..schemas import ParentIn, ParentOut, StudentIn, StudentOut

router = APIRouter(tags=["people"])


def _get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Не найдено")
    return obj


def _by_ids(db: Session, model, ids: list[int]):
    if not ids:
        return []
    rows = db.scalars(select(model).where(model.id.in_(ids))).all()
    if len(rows) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Указан несуществующий id")
    return list(rows)


# --- Ученики ----------------------------------------------------------------------


@router.get("/students", response_model=list[StudentOut])
def list_students(db: Session = Depends(get_db)):
    return db.scalars(
        select(Student).options(selectinload(Student.parents)).order_by(Student.full_name)
    ).all()


@router.post("/students", response_model=StudentOut, status_code=201)
def create_student(body: StudentIn, db: Session = Depends(get_db)):
    student = Student()
    _apply_student(db, student, body)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.put("/students/{student_id}", response_model=StudentOut)
def update_student(student_id: int, body: StudentIn, db: Session = Depends(get_db)):
    student = _get_or_404(db, Student, student_id)
    _apply_student(db, student, body)
    db.commit()
    db.refresh(student)
    return student


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, Student, student_id))
    db.commit()


def _apply_student(db: Session, student: Student, body: StudentIn) -> None:
    student.full_name = body.full_name.strip()
    student.group_name = body.group_name
    student.monthly_fee = body.monthly_fee
    student.notes = body.notes
    student.active = body.active
    parents = _by_ids(db, Parent, body.parent_ids)
    for p in body.new_parents:
        parents.append(Parent(full_name=p.full_name.strip(), phone=p.phone, notes=p.notes))
    student.parents = parents


# --- Родители ---------------------------------------------------------------------


@router.get("/parents", response_model=list[ParentOut])
def list_parents(db: Session = Depends(get_db)):
    return db.scalars(
        select(Parent).options(selectinload(Parent.students)).order_by(Parent.full_name)
    ).all()


@router.post("/parents", response_model=ParentOut, status_code=201)
def create_parent(body: ParentIn, db: Session = Depends(get_db)):
    parent = Parent()
    _apply_parent(db, parent, body)
    db.add(parent)
    db.commit()
    db.refresh(parent)
    return parent


@router.put("/parents/{parent_id}", response_model=ParentOut)
def update_parent(parent_id: int, body: ParentIn, db: Session = Depends(get_db)):
    parent = _get_or_404(db, Parent, parent_id)
    _apply_parent(db, parent, body)
    db.commit()
    db.refresh(parent)
    return parent


@router.delete("/parents/{parent_id}", status_code=204)
def delete_parent(parent_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, Parent, parent_id))
    db.commit()


def _apply_parent(db: Session, parent: Parent, body: ParentIn) -> None:
    parent.full_name = body.full_name.strip()
    parent.phone = body.phone
    parent.notes = body.notes
    parent.students = _by_ids(db, Student, body.student_ids)
