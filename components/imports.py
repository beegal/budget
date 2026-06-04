from __future__ import annotations

from web_helpers import esc


def import_button(validation: dict[str, object] | None) -> str:
    if not validation:
        return ""
    import_disabled = " disabled" if validation["problem_count"] else ""
    return f'<button name="action" value="import"{import_disabled}>Importation</button>'


def render_validation(validation: dict[str, object]) -> str:
    row_html = "".join(
        f"""<tr class="{"import-row-error" if row["errors"] else ""}">
  <td>{row["line"]}</td>
  <td>{esc(row["date"])}</td>
  <td>{esc(row["label"])}</td>
  <td>{esc(row["amount"])}</td>
  <td>{esc(row["comment"])}</td>
  <td>{esc("; ".join(row["errors"]))}</td>
</tr>"""
        for row in validation["rows"]
    )
    return f"""<div class="import-validation">
  <h2>Fichier à importer</h2>
  <table>
    <thead><tr><th>#</th><th>Date</th><th>Intitulé</th><th>Montant</th><th>Commentaire</th><th>Erreur</th></tr></thead>
    <tbody>{row_html or "<tr><td colspan='6'>Aucune ligne à valider.</td></tr>"}</tbody>
  </table>
  <div class="import-result">
    <div><span>Records corrects</span><strong>{validation["correct_count"]}</strong></div>
    <div><span>Records problématiques</span><strong class="{"negative" if validation["problem_count"] else "positive"}">{validation["problem_count"]}</strong></div>
    <div><span>Intitulés existants</span><strong>{validation["existing_label_count"]}</strong></div>
    <div><span>Intitulés à créer</span><strong>{validation["create_label_count"]}</strong></div>
  </div>
</div>"""
