# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google import genai
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_instruction import A2UI_INSTRUCTION
from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.8-flash"
GCP_PROJECT_ID = "qwiklabs-gcp-03-f8fbdbc5ec06"
GCS_BUCKET_NAME = "recipe-assistant-qwiklabs-gcp-03-f8fbdbc5ec06"
MEMORY_BANK_ID = "772487182861467648"


async def generate_memories_callback(callback_context: CallbackContext):
    """After each turn, automatically extracts and commits durable user facts/preferences to Memory Bank."""
    await callback_context.add_session_to_memory()
    return None


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded GCP project ID."""
    return firestore.Client(project=GCP_PROJECT_ID)


def list_recipes() -> List[Dict[str, Any]]:
    """Lists all available recipes from Firestore with basic overview details.

    Returns:
        A list of recipes with id, title, ingredients, prep time, difficulty, and cuisine.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()
    result = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        result.append(data)
    return result


def find_recipes_by_ingredients(on_hand_ingredients: List[str]) -> List[Dict[str, Any]]:
    """Finds recipes matching the ingredients the user has on hand.

    Args:
        on_hand_ingredients: List of ingredient strings the user has available.

    Returns:
        List of matching recipes with matched ingredients count and missing ingredients.
    """
    db = get_firestore_client()
    recipes_ref = db.collection("recipes")
    docs = recipes_ref.stream()

    cleaned_user_ingredients = [ing.strip().lower() for ing in on_hand_ingredients]
    matched_results = []

    for doc in docs:
        recipe = doc.to_dict()
        recipe["id"] = doc.id
        recipe_ingredients = [ing.lower() for ing in recipe.get("ingredients", [])]
        
        matched = [ing for ing in recipe_ingredients if any(user_ing in ing for user_ing in cleaned_user_ingredients)]
        missing = [ing for ing in recipe_ingredients if ing not in matched]

        match_score = len(matched)
        if match_score > 0:
            matched_results.append({
                "id": recipe["id"],
                "title": recipe.get("title"),
                "matched_ingredients": matched,
                "missing_ingredients": missing,
                "prep_time_minutes": recipe.get("prep_time_minutes"),
                "difficulty": recipe.get("difficulty"),
                "cuisine": recipe.get("cuisine"),
                "match_count": match_score
            })

    matched_results.sort(key=lambda x: x["match_count"], reverse=True)
    return matched_results


def get_recipe_details(recipe_id: str) -> Dict[str, Any]:
    """Retrieves full details for a recipe, including cooking instructions and nutrition.

    Args:
        recipe_id: The unique ID of the recipe to retrieve.

    Returns:
        A dictionary containing the full recipe details or an error message if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection("recipes").document(recipe_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"error": f"Recipe with ID '{recipe_id}' not found."}
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def save_recipe(
    recipe_id: str,
    title: str,
    ingredients: List[str],
    instructions: List[str],
    prep_time_minutes: int,
    difficulty: str = "Easy",
    cuisine: str = "General",
    is_favorite: bool = False
) -> Dict[str, Any]:
    """Saves or updates a recipe in Firestore.

    Args:
        recipe_id: Unique slug/id for the recipe (e.g. 'quick-quesadilla').
        title: Title of the recipe.
        ingredients: List of required ingredients.
        instructions: Step-by-step cooking instructions.
        prep_time_minutes: Preparation time in minutes.
        difficulty: Difficulty level (e.g., Easy, Medium, Hard).
        cuisine: Cuisine style.
        is_favorite: Whether this recipe is marked as a favorite.

    Returns:
        A dictionary confirming the recipe was saved.
    """
    db = get_firestore_client()
    doc_ref = db.collection("recipes").document(recipe_id)
    data = {
        "id": recipe_id,
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "prep_time_minutes": prep_time_minutes,
        "difficulty": difficulty,
        "cuisine": cuisine,
        "is_favorite": is_favorite,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }
    doc_ref.set(data, merge=True)
    return {"status": "success", "message": f"Recipe '{title}' saved successfully.", "recipe": data}


def toggle_favorite_recipe(recipe_id: str, is_favorite: bool) -> Dict[str, Any]:
    """Marks or unmarks a recipe as a favorite in Firestore.

    Args:
        recipe_id: The ID of the recipe.
        is_favorite: Boolean flag indicating if the recipe is a favorite.

    Returns:
        Status of the update.
    """
    db = get_firestore_client()
    doc_ref = db.collection("recipes").document(recipe_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"error": f"Recipe '{recipe_id}' not found."}
    doc_ref.update({"is_favorite": is_favorite})
    return {"status": "success", "message": f"Recipe '{recipe_id}' favorite status set to {is_favorite}."}


def get_ingredient_substitutes(ingredient: str) -> Dict[str, Any]:
    """Provides common cooking substitutes for a missing ingredient.

    Args:
        ingredient: Name of the missing ingredient (e.g. 'butter', 'heavy cream', 'egg', 'soy sauce', 'garlic').

    Returns:
        A dictionary with the original ingredient and recommended alternatives with ratios and tips.
    """
    substitutions: Dict[str, List[Dict[str, str]]] = {
        "butter": [
            {"substitute": "Olive oil or vegetable oil", "ratio": "3/4 cup oil per 1 cup butter", "note": "Great for cooking or quick breads; not for laminated pastry."},
            {"substitute": "Greek yogurt or applesauce", "ratio": "1:1 ratio", "note": "Best for baking to cut fat and add moisture."}
        ],
        "heavy cream": [
            {"substitute": "Milk + Melted Butter", "ratio": "3/4 cup milk + 1/4 cup melted butter for 1 cup heavy cream", "note": "Good for sauces and soups; cannot be whipped."},
            {"substitute": "Coconut milk (full fat)", "ratio": "1:1 ratio", "note": "Dairy-free option with slight coconut flavor."}
        ],
        "egg": [
            {"substitute": "Flax egg (ground flaxseed + water)", "ratio": "1 tbsp ground flax + 3 tbsp water per egg", "note": "Let rest 5 mins; excellent for baking."},
            {"substitute": "Applesauce or mashed banana", "ratio": "1/4 cup per egg", "note": "Adds moisture and binding for sweet baked goods."}
        ],
        "soy sauce": [
            {"substitute": "Tamari", "ratio": "1:1 ratio", "note": "Gluten-free direct alternative."},
            {"substitute": "Worcestershire sauce + splash of water", "ratio": "1:1 ratio", "note": "Deep savory umami flavor."}
        ],
        "garlic": [
            {"substitute": "Garlic powder", "ratio": "1/8 tsp garlic powder per 1 clove fresh garlic", "note": "Concentrated flavor, dissolve into liquid."},
            {"substitute": "Shallots or chives", "ratio": "1 tbsp minced per clove", "note": "Milder allium aroma."}
        ],
        "parmesan": [
            {"substitute": "Pecorino Romano", "ratio": "1:1 ratio", "note": "Slightly saltier and sharper sheep's milk cheese."},
            {"substitute": "Nutritional yeast", "ratio": "1:1 ratio", "note": "Vegan cheesy, nutty alternative."}
        ],
        "rice": [
            {"substitute": "Quinoa or riced cauliflower", "ratio": "1:1 cooked ratio", "note": "Lower carb or higher protein alternative."},
            {"substitute": "Orzo or small pasta", "ratio": "1:1 cooked ratio", "note": "Great starchy side alternative."}
        ]
    }

    cleaned = ingredient.strip().lower()
    for key, alts in substitutions.items():
        if key in cleaned or cleaned in key:
            return {"ingredient": ingredient, "found": True, "substitutes": alts}

    return {
        "ingredient": ingredient,
        "found": False,
        "message": f"No pre-configured substitution found for '{ingredient}'. Suggesting culinary general substitute based on function (acid, fat, binder, or seasoning)."
    }


def search_online_recipes(query: str) -> Dict[str, Any]:
    """Searches a public recipe database (TheMealDB) for real culinary recipes by dish name or keyword.

    Args:
        query: Name of the dish, cuisine, or main ingredient to search online for (e.g., 'curry', 'pasta', 'arrabiata', 'chicken').

    Returns:
        A dictionary containing online recipe search results with dish title, cuisine, category, instructions, and ingredients.
    """
    api_key = os.getenv("MEALDB_API_KEY", "1")  # '1' is the free public test key provided by TheMealDB
    encoded_query = urllib.parse.quote(query.strip())
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={encoded_query}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RecipeAssistantAgent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status != 200:
                return {"error": f"API request failed with status code {response.status}"}
            data = json.loads(response.read().decode())
    except Exception as e:
        return {"error": f"Failed to fetch recipes from online API: {str(e)}"}

    raw_meals = data.get("meals")
    if not raw_meals:
        return {"query": query, "found": False, "results": [], "message": f"No online recipes found for '{query}'."}

    results = []
    for meal in raw_meals[:3]:
        ingredients = []
        for i in range(1, 21):
            ing = meal.get(f"strIngredient{i}")
            measure = meal.get(f"strMeasure{i}")
            if ing and ing.strip():
                item = f"{measure.strip()} {ing.strip()}".strip() if measure else ing.strip()
                ingredients.append(item)

        results.append({
            "title": meal.get("strMeal"),
            "category": meal.get("strCategory"),
            "cuisine": meal.get("strArea"),
            "instructions": meal.get("strInstructions", "").strip(),
            "ingredients": ingredients,
            "thumbnail_url": meal.get("strMealThumb"),
            "source_url": meal.get("strSource"),
        })

    return {"query": query, "found": True, "count": len(results), "results": results}


def geocode_address(address: str) -> Dict[str, Any]:
    """Converts an address or location name into geographic latitude and longitude coordinates using Google Maps Geocoding API.

    Args:
        address: The address, city, or zip code (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'Seattle, WA').

    Returns:
        A dictionary containing formatted address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}

    encoded_address = urllib.parse.quote(address.strip())
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RecipeAssistantAgent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}

    status = data.get("status")
    if status != "OK" or not data.get("results"):
        return {
            "address": address,
            "error": f"Geocoding failed with status: {status}",
            "message": data.get("error_message", "No results found.")
        }

    first_result = data["results"][0]
    location = first_result.get("geometry", {}).get("location", {})
    return {
        "address": address,
        "formatted_address": first_result.get("formatted_address"),
        "location": {
            "latitude": location.get("lat"),
            "longitude": location.get("lng")
        }
    }


def find_nearby_places(
    place_type: str = "supermarket",
    latitude: float = 40.7128,
    longitude: float = -74.0060,
    radius_meters: float = 3000.0,
    max_results: int = 5
) -> Dict[str, Any]:
    """Finds nearby places of a given type (e.g. supermarket, grocery_store, bakery) using Google Places API (New).

    Args:
        place_type: Type of place to search for (e.g. 'supermarket', 'grocery_store', 'bakery', 'convenience_store').
        latitude: Latitude coordinate for the center of the search area.
        longitude: Longitude coordinate for the center of the search area.
        radius_meters: Search radius in meters (default is 3000m / 3km).
        max_results: Maximum number of places to return (up to 10).

    Returns:
        A list of nearby places with name, formatted address, location coordinates, and rating.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types,places.rating"
    }

    body = json.dumps({
        "includedTypes": [place_type.strip().lower()],
        "maxResultCount": min(max(1, max_results), 10),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": float(radius_meters)
            }
        }
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        return {"error": f"Places API returned HTTP {e.code}: {err_msg}"}
    except Exception as e:
        return {"error": f"Failed to call Places API: {str(e)}"}

    places = data.get("places", [])
    results = []
    for p in places:
        name_obj = p.get("displayName", {})
        results.append({
            "name": name_obj.get("text") if isinstance(name_obj, dict) else str(name_obj),
            "address": p.get("formattedAddress"),
            "location": p.get("location"),
            "types": p.get("types", []),
            "rating": p.get("rating")
        })

    return {
        "place_type": place_type,
        "search_center": {"latitude": latitude, "longitude": longitude},
        "count": len(results),
        "places": results
    }


async def generate_recipe_image(
    recipe_name: str,
    tool_context: ToolContext,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Generates an appetizing presentation photo of a cooked recipe or dish using gemini-3.1-flash-lite-image.

    Saves the image as an artifact for the playground and uploads it to the public Cloud Storage bucket.

    Args:
        recipe_name: The name of the recipe or meal (e.g. 'Spicy Arrabiata Penne', 'Garlic Butter Pasta').
        tool_context: ADK ToolContext used to save artifacts to the playground session.
        description: Optional culinary visual details (e.g., 'garnished with fresh basil leaves and shredded parmesan').

    Returns:
        A dictionary with the public image URL, bucket name, and artifact details.
    """
    prompt = f"Professional food photography of {recipe_name}."
    if description:
        prompt += f" {description}."
    prompt += " Plated beautifully on a modern dining plate, warm restaurant lighting, sharp focus, vibrant food colors, 4k quality."

    try:
        # Initialize Google GenAI client in global region
        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=dict(response_modalities=["IMAGE"])
        )

        image_bytes = None
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if image_bytes:
                break

        if not image_bytes:
            return {"error": "No image data was generated by the model."}

        # 1. Save artifact in the Playground session
        artifact_filename = f"{recipe_name.lower().replace(' ', '_')}_{int(datetime.datetime.utcnow().timestamp())}.jpg"
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        await tool_context.save_artifact(
            filename=artifact_filename,
            artifact=image_part
        )

        # 2. Upload bytes directly to Cloud Storage bucket (without saving locally)
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"recipe_images/{artifact_filename}")
        blob.upload_from_string(image_bytes, content_type="image/jpeg")

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/recipe_images/{artifact_filename}"

        return {
            "status": "success",
            "recipe_name": recipe_name,
            "artifact_saved": artifact_filename,
            "public_url": public_url,
            "message": f"Generated image for '{recipe_name}' and published to Cloud Storage."
        }

    except Exception as e:
        return {"error": f"Failed to generate recipe image: {str(e)}"}


async def generate_recipe_video(
    recipe_name: str,
    tool_context: ToolContext,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Generates a short, appetizing cooking or plating video for a recipe or dish using gemini-omni-flash-preview.

    Saves the video as an artifact for the playground and uploads the video bytes to the public Cloud Storage bucket.

    Args:
        recipe_name: The name of the recipe or meal (e.g. 'Sizzling Garlic Butter Pasta', 'Crispy Golden Quesadilla').
        tool_context: ADK ToolContext used to save artifacts to the playground session.
        description: Optional culinary visual details (e.g., 'sizzling in a skillet with melting butter and fresh herbs').

    Returns:
        A dictionary with the public video URL and artifact details.
    """
    prompt = f"A short, cinematic, professional video of {recipe_name}."
    if description:
        prompt += f" {description}."
    prompt += " Beautiful restaurant kitchen presentation, appetizing motion, sharp focus, 720p."

    try:
        # Initialize Google GenAI client in global region
        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location="global")
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
            response_format={"type": "video", "resolution": "720p"}
        )

        output_video = getattr(interaction, "output_video", None)
        if not output_video:
            return {"error": "No video was returned by the gemini-omni-flash-preview model."}

        # Extract video bytes from output_video
        raw_data = getattr(output_video, "data", None)
        if isinstance(output_video, dict) and not raw_data:
            raw_data = output_video.get("data")

        if not raw_data:
            return {"error": "Output video contains no data."}

        if isinstance(raw_data, str):
            video_bytes = base64.b64decode(raw_data)
        elif isinstance(raw_data, (bytes, bytearray)):
            video_bytes = bytes(raw_data)
        else:
            return {"error": f"Unexpected video data format: {type(raw_data)}"}

        mime_type = getattr(output_video, "mime_type", None) or "video/mp4"

        # (1) Save it with tool_context.save_artifact so it shows up in the Playground's Artifacts panel
        artifact_filename = f"{recipe_name.lower().replace(' ', '_')}_{int(datetime.datetime.utcnow().timestamp())}.mp4"
        video_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(
            filename=artifact_filename,
            artifact=video_part
        )

        # (2) Upload the same video bytes directly to the public Cloud Storage bucket and return public URL
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(f"recipe_videos/{artifact_filename}")
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/recipe_videos/{artifact_filename}"

        return {
            "status": "success",
            "recipe_name": recipe_name,
            "artifact_saved": artifact_filename,
            "public_url": public_url,
            "message": f"Generated video for '{recipe_name}' and published to Cloud Storage."
        }

    except Exception as e:
        return {"error": f"Failed to generate recipe video: {str(e)}"}


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=A2UI_INSTRUCTION,
    tools=[
        PreloadMemoryTool(),
        list_recipes,
        find_recipes_by_ingredients,
        get_recipe_details,
        save_recipe,
        toggle_favorite_recipe,
        get_ingredient_substitutes,
        search_online_recipes,
        geocode_address,
        find_nearby_places,
        generate_recipe_image,
        generate_recipe_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

