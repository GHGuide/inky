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


def classify(action, el, page=None):
    """-> (verdict, why). verdict: ok | irreversible | pay | password | robot"""
    if page and page.get("robot"):
        return "robot", "the page shows a robot check"
    if not el:
        return "ok", ""
    if action in ("fill", "type") and (el.get("role") == "password" or el.get("type") == "password"):
        return "password", "that is a password field"
    if action in ("click", "press") and (el.get("role") in ("button", "link") or el.get("type") == "submit"):
        label = " ".join(filter(None, [el.get("name"), el.get("text")]))
        w = _has(PAY, label)
        if w:
            return "pay", f"“{label}” would spend money"
        w = _has(IRREVERSIBLE, label)
        if w:
            return "irreversible", f"“{label}” can’t be undone"
    return "ok", ""
