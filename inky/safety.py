"""What a bot may do on its own. Irreversible clicks wait for you; paying is never allowed by default;
password fields and robot checks are always yours."""
import re

PAY = ["buy", "purchase", "pay", "checkout", "check out", "place order", "order now", "add to cart", "acquista", "compra",
       "paga", "pagar", "comprar", "kopen", "betalen", "bestellen", "kup", "zapłać", "zamów", "kaufen", "bezahlen",
       "acheter", "payer", "commander"]
IRREVERSIBLE = ["send", "submit", "delete", "delete account", "confirm", "sign up", "register", "create account", "subscribe",
                "publish", "post", "apply now", "submit application", "book", "reserve", "transfer", "unsubscribe", "cancel order",
                "invia", "inviare", "conferma", "elimina", "iscriviti", "registrati", "prenota", "pubblica",
                "enviar", "eliminar", "confirmar", "reservar", "suscribirse", "publicar",
                "versturen", "verzenden", "verwijderen", "aanmelden", "boeken", "bevestigen",
                "wyślij", "usuń", "zarejestruj", "potwierdź", "senden", "löschen", "bestätigen", "buchen", "absenden",
                "envoyer", "supprimer", "confirmer", "réserver", "s'inscrire"]


def _has(words, text):
    t = (text or "").lower()
    return next((w for w in words if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", t)), None)


LOGIN = ["log in", "login", "sign in", "signin", "accedi", "entra", "anmelden", "einloggen", "se connecter", "connexion", "inloggen",
         "iniciar sesión", "entrar", "zaloguj", "zaloguj się", "continue with"]


def classify(action, el, page=None):
    """-> (verdict, why). verdict: ok | irreversible | pay | password | robot"""
    if page and page.get("robot"):
        return "robot", "the page shows a robot check"
    if not el:
        return "ok", ""
    if action in ("fill", "type") and (el.get("role") == "password" or el.get("type") == "password"):
        return "password", "that is a password field"
    form = el.get("form") or {}
    # pressing a form's button, or Enter in one of its boxes, sends that form
    submits = action in ("click", "press") and (form.get("submits") or (action == "press" and el.get("role") in ("textbox", "password", "combobox")))
    label = el.get("name") or el.get("text") or ""
    if el.get("text") and el.get("text") != label:
        label = f"{label} {el['text']}"
    button = action in ("click", "press") and (el.get("role") in ("button", "link") or el.get("type") == "submit")
    if button and _has(PAY, label):
        return "pay", f"“{label}” would spend money"
    if (submits and form.get("password")) or (button and el.get("role") == "button" and (page or {}).get("pw") and _has(LOGIN, label)):
        return "password", "that signs in"  # whatever its button says (“Accedi”, “Continue”): only you sign in
    if button and _has(IRREVERSIBLE, label):
        return "irreversible", f"“{label}” can’t be undone"
    if submits and form.get("post") and form.get("personal"):  # a contact, sign-up or order form; not a page-wide ASP.NET form
        return "irreversible", f"“{label or 'that'}” sends a form"
    return "ok", ""
