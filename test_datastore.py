# test_datastore.py
import sys
sys.path.insert(0, r"D:\dream_project\daily_mate_code\demo_server")
import data_store

data_store.load_all()
stats = data_store.get_stats()
print("Stats:", stats)

dish = data_store.get_dish_by_id(1)
print("Dish ID 1:", dish)

ings = data_store.get_ingredients_for_dish(1)
print("Dish 1 ingredients count:", len(ings))
if ings:
    print("First ingredient:", ings[0])

tmpl = data_store.get_advice_templates("weather", "heat_stress", "high")
print("Advice templates (weather/heat_stress/high):", len(tmpl))
