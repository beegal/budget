from __future__ import annotations

from datetime import date, datetime, timedelta

from database import db
from web_helpers import esc, layout, money, one, period_label


def page() -> bytes:
    with db() as conn:
        periods = conn.execute(
            """
            SELECT m.*,
                   COUNT(t.id) AS transaction_count,
                   COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount END), 0) AS income,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN t.amount END), 0) AS expense,
                   COALESCE(SUM(t.amount), 0) AS net
            FROM months m
            LEFT JOIN transactions t ON t.month_id = m.id
            GROUP BY m.id
            ORDER BY m.id DESC
            """
        ).fetchall()
    cards = "".join(
        f"""<article class="card">
  <div class="muted">{esc(period_label(row))}</div>
  <h2>{esc(row["name"])}</h2>
  <dl class="metrics">
    <div><dt>Entrées</dt><dd class="positive">{money(row["income"])}</dd></div>
    <div><dt>Sorties</dt><dd class="negative">{money(row["expense"])}</dd></div>
    <div><dt>Net</dt><dd>{money(row["net"])}</dd></div>
  </dl>
  <a class="button ghost" href="/period/{row["id"]}">Ouvrir</a>
</article>"""
        for row in periods
    )
    body = f"""<section class="page-title">
  <div>
    <p class="eyebrow">Application budget générique</p>
    <h1>Périodes</h1>
  </div>
</section>
<section class="panel create-strip">
  <form method="post" action="/periods/create" class="inline-form">
    <input name="name" placeholder="Nom, ex. Juin-Juillet" required>
    <label class="compact-label">Début
      <input type="date" name="start_date" value="{date.today().isoformat()}" required>
    </label>
    <button>Créer la période</button>
  </form>
</section>
<section class="grid">{cards}</section>"""
    return layout("Périodes", body)


def create(data: dict[str, list[str]]) -> str:
    start_date = datetime.strptime(one(data, "start_date"), "%Y-%m-%d").date()
    previous_end_date = (start_date - timedelta(days=1)).isoformat()
    period = f"{start_date.isoformat()} -> en cours"
    with db() as conn:
        conn.execute(
            """
            UPDATE months
            SET end_date = ?, period = start_date || ' -> ' || ?
            WHERE start_date IS NOT NULL AND end_date IS NULL AND start_date < ?
            """,
            (previous_end_date, previous_end_date, start_date.isoformat()),
        )
        conn.execute(
            "INSERT INTO months(name, period, start_date, end_date) VALUES (?, ?, ?, NULL)",
            (one(data, "name"), period, start_date.isoformat()),
        )
        month_id = conn.execute("SELECT id FROM months WHERE name = ?", (one(data, "name"),)).fetchone()["id"]
        account_ids = conn.execute("SELECT id FROM accounts").fetchall()
        for account in account_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO account_balances(month_id, account_id, opening, current, closing, difference)
                VALUES (?, ?, 0, 0, 0, 0)
                """,
                (month_id, account["id"]),
            )
        seed_budget_schedule(conn, month_id)
    return "/"


def seed_budget_schedule(conn, month_id: int) -> None:
    conn.execute(
        """
        INSERT INTO budget_schedule(month_id, label, amount, status)
        SELECT ?, label, amount, 'scheduled'
        FROM monthly_budget
        ORDER BY day, id
        """,
        (month_id,),
    )
