import kagglehub
import pandas as pd
import os

# Load dataset
path = kagglehub.dataset_download(
    "raymondtoo/the-world-university-rankings-2016-2024"
)

# Find the CSV file in the downloaded path
csv_files = [f for f in os.listdir(path) if f.endswith('.csv')]
csv_path = os.path.join(path, csv_files[0])
df = pd.read_csv(csv_path)

# Inspect columns
print("Original columns:", df.columns.tolist())


# Filter to latest year
latest_year = df['Year'].max()
df = df[df['Year'] == latest_year].copy()

# Keep only required columns and rename
df = df[['Name', 'Country', 'Rank']].copy()
df.columns = ['name', 'country', 'rank']

# Drop missing values
df = df.dropna(subset=['name', 'rank'])

# Convert rank to numeric (handle ranges like "51-100")
df['rank'] = df['rank'].astype(str).str.split('-').str[0].str.replace('+', '').str.strip()
df['rank'] = pd.to_numeric(df['rank'], errors='coerce')
df = df.dropna(subset=['rank'])
df['rank'] = df['rank'].astype(int)

# Create ranking_band
def get_ranking_band(rank):
    if rank <= 50:
        return "Top 50"
    elif rank <= 100:
        return "50-100"
    elif rank <= 300:
        return "100-300"
    else:
        return "300+"

df['ranking_band'] = df['rank'].apply(get_ranking_band)

# Create competitiveness
def get_competitiveness(band):
    mapping = {
        "Top 50": "HIGH",
        "50-100": "MEDIUM",
        "100-300": "LOW",
        "300+": "VERY_LOW"
    }
    return mapping[band]

df['competitiveness'] = df['ranking_band'].apply(get_competitiveness)

# Create avg_tuition_usd
def get_tuition(country):
    tuition_map = {
        "United States": 40000,
        "United Kingdom": 30000,
        "Canada": 25000,
        "Australia": 28000,
        "Germany": 2000
    }
    return tuition_map.get(country, 20000)

df['avg_tuition_usd'] = df['country'].apply(get_tuition)

# Save to CSV
df.to_csv('universities_canonical.csv', index=False)

# Print total
print(f"Total universities after cleaning: {len(df)}")
