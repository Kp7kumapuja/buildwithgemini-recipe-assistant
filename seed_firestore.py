from google.cloud import firestore

GCP_PROJECT_ID = "qwiklabs-gcp-03-f8fbdbc5ec06"

recipes = [
    {
        "id": "garlic-butter-pasta",
        "title": "Garlic Butter Parmesan Pasta",
        "ingredients": ["pasta", "garlic", "butter", "parmesan", "black pepper"],
        "prep_time_minutes": 15,
        "difficulty": "Easy",
        "instructions": [
            "Boil pasta in salted water until al dente.",
            "In a skillet, melt butter over medium-low heat and gently sauté minced garlic until fragrant.",
            "Toss cooked pasta into the garlic butter skillet with a splash of pasta water.",
            "Stir in grated parmesan and cracked black pepper until creamy. Serve hot."
        ],
        "is_favorite": True,
        "cuisine": "Italian",
        "nutrition": {"calories": 420, "protein": 12, "carbs": 58, "fat": 16}
    },
    {
        "id": "quick-egg-fried-rice",
        "title": "Quick Egg Fried Rice",
        "ingredients": ["rice", "eggs", "soy sauce", "green onions", "oil", "garlic"],
        "prep_time_minutes": 12,
        "difficulty": "Easy",
        "instructions": [
            "Heat oil in a wok or large pan over high heat.",
            "Beat eggs lightly and scramble quickly in the pan, then push aside.",
            "Add minced garlic and cold cooked rice, breaking up clumps.",
            "Drizzle with soy sauce and toss everything together until heated through.",
            "Garnish with sliced green onions and serve immediately."
        ],
        "is_favorite": False,
        "cuisine": "Asian",
        "nutrition": {"calories": 380, "protein": 14, "carbs": 52, "fat": 13}
    },
    {
        "id": "tomato-basil-bruschetta",
        "title": "Crispy Tomato Basil Bruschetta",
        "ingredients": ["bread", "tomatoes", "basil", "olive oil", "garlic", "salt"],
        "prep_time_minutes": 10,
        "difficulty": "Easy",
        "instructions": [
            "Dice tomatoes and combine with chopped fresh basil, olive oil, and a pinch of salt.",
            "Slice and toast bread slices until golden and crisp.",
            "Rub the warm toasted bread lightly with a peeled raw garlic clove.",
            "Spoon tomato basil mixture generously over each slice."
        ],
        "is_favorite": True,
        "cuisine": "Mediterranean",
        "nutrition": {"calories": 210, "protein": 6, "carbs": 28, "fat": 9}
    },
    {
        "id": "classic-omelette",
        "title": "Classic Fluffy Cheese Omelette",
        "ingredients": ["eggs", "butter", "cheese", "salt", "pepper"],
        "prep_time_minutes": 8,
        "difficulty": "Easy",
        "instructions": [
            "Whisk eggs with a pinch of salt and pepper.",
            "Melt butter in a nonstick skillet over medium-low heat.",
            "Pour in eggs and gently pull edges to the center as curds form.",
            "Sprinkle shredded cheese across the center, fold, and slide onto a warm plate."
        ],
        "is_favorite": False,
        "cuisine": "American",
        "nutrition": {"calories": 310, "protein": 19, "carbs": 2, "fat": 25}
    }
]

def seed():
    db = firestore.Client(project=GCP_PROJECT_ID)
    collection_ref = db.collection("recipes")
    for r in recipes:
        collection_ref.document(r["id"]).set(r)
        print(f"Seeded recipe: {r['title']} ({r['id']})")

if __name__ == "__main__":
    seed()
