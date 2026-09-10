import os
import pathlib

REQUIRED_DIRS = [
    "downloads",
    "utils",
    "services",
    "bot",
]

INIT_LOCATIONS = [
    os.path.join("utils", "__init__.py"),
    os.path.join("services", "__init__.py"),
    os.path.join("bot", "__init__.py"),
]


def run_preflight_checks():
  print("\n" + "=" * 60)
  print("🛠️  RUNNING PREFLIGHT SETUP CHECKS FOR STREAMLIT CLOUD")
  print("=" * 60)

  # 1. Verify / Create Directories
  for d in REQUIRED_DIRS:
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    print(f"✅ Verified directory: ./{d}")

  # 2. Verify / Create __init__.py files
  for init_path in INIT_LOCATIONS:
    if not os.path.exists(init_path):
      with open(init_path, "w", encoding="utf-8") as f:
        f.write("# Package marker\n")
      print(f"✨ Created missing marker: {init_path}")
    else:
      print(f"✅ Found marker: {init_path}")

  # 3. Check Font Existence
  font_path = "THUMBA-Bold.ttf"
  if os.path.exists(font_path):
    print(f"✅ Font detected: {font_path}")
  else:
    print(f"⚠️  WARNING: '{font_path}' not found in root directory!")

  print("\n🚀 Preflight complete! You can deploy to Streamlit Cloud.")
  print("=" * 60 + "\n")


if __name__ == "__main__":
  run_preflight_checks()

