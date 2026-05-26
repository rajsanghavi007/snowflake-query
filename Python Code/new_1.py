import pandas as pd
import re
from rapidfuzz import fuzz

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

CEEB_DTYPE = {
    'hs_ceeb_code': str,
    'ceeb_cd': str,
    'ceeb_code': str,
    'ceeb': str,
    'hs_ceeb': str
}

SOURCE_PRIORITY = {
    'SC': 1,
    'Enroll360': 2,
    'CAPPEX': 3,
    'PAPA': 4
}

RENAME_DICT = {
    # CEEB code mappings
    'hs_ceeb_code': 'hs_ceeb_code',
    'ceeb_cd': 'hs_ceeb_code',
    'ceeb_code': 'hs_ceeb_code',
    'ceeb': 'hs_ceeb_code',
    'hs_ceeb': 'hs_ceeb_code',

    # School name mappings
    'school_name': 'school_name',
    'name': 'school_name',
    'hs_name': 'school_name',

    # Address1 mappings
    'address1': 'address1',
    'addr1': 'address1',
    'address_line_1': 'address1',

    # Address2 mappings
    'address2': 'address2',
    'addr2': 'address2',
    'address_line_2': 'address2',

    # City mappings
    'city': 'city',

    # State mappings
    'state': 'state',

    # Zip mappings
    'zip': 'zip',
    'zip_code': 'zip',
    'zip5': 'zip',

    # Country mappings
    'country': 'country'
}

# Post-selection cleanup only.
# Keep this list small and high-confidence.
ABBREVIATION_MAP = {
    r'\bCOMMU\b': 'COMMUNITY',
    r'\bCOMM\b': 'COMMUNITY',
    r'\bCTR\b': 'CENTER',
    r'\bCTRS\b': 'CENTERS',
    r'\bACAD\b': 'ACADEMY',
    r'\bINST\b': 'INSTITUTE',
    r'\bALT\b': 'ALTERNATIVE',
    r'\bSCH\b': 'SCHOOL',
    r'\bMLTRY\b': 'MILITARY',
    r'\bACAD\b': 'ACADEMY',
    r'\bCOLL\b': 'COLLEGE',
    r'\bUNIV\b': 'UNIVERSITY',
    r'\bCLG\b': 'COLLEGE'
}


# -----------------------------------------------------------------------------
# FILE LOADING
# -----------------------------------------------------------------------------

def load_files():
    file1 = pd.read_csv('final_addr2.csv', dtype=CEEB_DTYPE)
    file2 = pd.read_csv('CAPPEX_DB.DBT.B_CPX_REFERENCE_DATA_HIGH_SCHOOL.csv', dtype=CEEB_DTYPE)
    file3 = pd.read_excel('HS Ceeb Code file_PAPA.xlsx', dtype=CEEB_DTYPE, engine='openpyxl')
    file4 = pd.read_csv('CROSS_TENANT_DB.COMMON.REF__HIGH_SCHOOLS.csv', dtype=CEEB_DTYPE)
    return file1, file2, file3, file4


# -----------------------------------------------------------------------------
# STANDARDIZATION HELPERS
# -----------------------------------------------------------------------------

def lowercase_columns(df):
    df.columns = df.columns.str.lower()
    return df


def standardize_columns(df):
    return df.rename(columns=RENAME_DICT)


def standardize_ceeb_code(df, col_name='hs_ceeb_code'):
    """
    Keep ceeb code as-is after trimming and removing trailing .0.
    No zero-fill padding.
    Example:
      88 -> 88
      000088 -> 000088
    """
    if col_name in df.columns:
        df[col_name] = (
            df[col_name]
            .astype(str)
            .str.strip()
            .str.replace(r'\.0$', '', regex=True)
        )

        df[col_name] = df[col_name].replace({
            'nan': pd.NA,
            'None': pd.NA,
            '': pd.NA
        })

    return df


def normalize_school_name(name):
    if pd.isna(name):
        return pd.NA

    name = str(name).strip()
    if not name:
        return pd.NA

    return name.title()


def normalize_text(val):
    if pd.isna(val):
        return pd.NA

    val = str(val).strip()
    if not val:
        return pd.NA

    return val.title()


def normalize_zip(val):
    if pd.isna(val):
        return pd.NA

    val = str(val).strip().replace('.0', '')
    if not val:
        return pd.NA

    return val


def normalize_state(val):
    if pd.isna(val):
        return pd.NA

    val = str(val).strip()
    if not val:
        return pd.NA

    return val.upper()


def normalize_country(val):
    if pd.isna(val):
        return pd.NA

    val = str(val).strip()
    if not val:
        return pd.NA

    return val.upper()


def normalize_dataframe(df):
    if 'school_name' in df.columns:
        df['school_name'] = df['school_name'].apply(normalize_school_name)

    if 'address1' in df.columns:
        df['address1'] = df['address1'].apply(normalize_text)

    if 'address2' in df.columns:
        df['address2'] = df['address2'].apply(normalize_text)

    if 'city' in df.columns:
        df['city'] = df['city'].apply(normalize_text)

    if 'state' in df.columns:
        df['state'] = df['state'].apply(normalize_state)

    if 'zip' in df.columns:
        df['zip'] = df['zip'].apply(normalize_zip)

    if 'country' in df.columns:
        df['country'] = df['country'].apply(normalize_country)

    return df


def add_prefix(df, prefix, key='hs_ceeb_code'):
    return df.rename(columns={
        col: f'{prefix}{col}' for col in df.columns if col != key
    })


# -----------------------------------------------------------------------------
# GENERIC RESOLUTION HELPERS
# -----------------------------------------------------------------------------

def first_non_null_by_priority(row, cols):
    for col in cols:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col]).strip()
    return None


def get_existing_columns(df, cols):
    return [col for col in cols if col in df.columns]


# -----------------------------------------------------------------------------
# SCHOOL NAME RESOLUTION
# -----------------------------------------------------------------------------

def source_from_col(col_name):
    if col_name.startswith('SC_'):
        return 'SC'
    if col_name.startswith('Enroll360_'):
        return 'Enroll360'
    if col_name.startswith('CAPPEX_'):
        return 'CAPPEX'
    if col_name.startswith('PAPA_'):
        return 'PAPA'
    return 'ZZZ'


def normalize_school_name_for_match(name):
    """
    Matching-only normalization.
    No semantic replacements like COMM -> COMMUNITY,
    HS -> HIGH SCHOOL, or ST -> SAINT.
    Only basic cleanup for fuzzy comparison.
    """
    if pd.isna(name):
        return None

    name = str(name).strip().upper()
    if not name:
        return None

    name = name.replace('&', ' AND ')
    name = re.sub(r'[^A-Z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def is_abbreviation(name):
    if pd.isna(name):
        return False

    name = str(name).strip()
    if not name:
        return False

    letters_only = re.sub(r'[^A-Za-z]', '', name)

    if 1 <= len(letters_only) <= 5:
        return True

    if name.count('.') >= 2:
        return True

    tokens = re.findall(r'[A-Za-z]+', name)
    if tokens and sum(len(t) <= 2 for t in tokens) / len(tokens) >= 0.6:
        return True

    return False


def build_similarity_graph(entries, threshold=90):
    """
    Create graph where each node is a school-name candidate.
    Two nodes are connected if fuzzy similarity >= threshold.
    """
    graph = {i: set() for i in range(len(entries))}

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            name1 = entries[i]['match_name']
            name2 = entries[j]['match_name']

            if not name1 or not name2:
                continue

            score = fuzz.token_set_ratio(name1, name2)

            if score >= threshold:
                graph[i].add(j)
                graph[j].add(i)

    return graph


def get_connected_components(graph):
    visited = set()
    components = []

    for node in graph:
        if node in visited:
            continue

        stack = [node]
        component = []

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)
            component.append(current)

            for neighbor in graph[current]:
                if neighbor not in visited:
                    stack.append(neighbor)

        components.append(component)

    return components


def score_cluster(cluster_entries):
    """
    Score cluster by:
    1. number of agreeing entries
    2. number of unique sources
    3. best source rank in cluster
    4. longest supported name
    """
    unique_sources = {e['source'] for e in cluster_entries}
    best_source_rank = min(SOURCE_PRIORITY.get(e['source'], 999) for e in cluster_entries)
    longest_name = max(len(e['original_name']) for e in cluster_entries)

    return (
        len(cluster_entries),
        len(unique_sources),
        -best_source_rank,
        longest_name
    )


def score_candidate(entry, support_count):
    """
    Score a candidate inside the winning cluster.
    Higher score is better.
    """
    source_rank = SOURCE_PRIORITY.get(entry['source'], 999)
    abbreviation_penalty = 1 if is_abbreviation(entry['original_name']) else 0
    length_score = min(len(entry['original_name']), 60)

    return (
        support_count,         # more agreement wins
        -source_rank,          # better source wins
        -abbreviation_penalty, # prefer non-abbreviation
        length_score           # prefer fuller name
    )


def get_best_school_name(row, school_name_cols, threshold=90):
    entries = []

    for col in school_name_cols:
        val = row.get(col, pd.NA)

        if pd.notna(val) and str(val).strip():
            original_name = str(val).strip()

            entries.append({
                'original_name': original_name,
                'match_name': normalize_school_name_for_match(original_name),
                'source': source_from_col(col),
                'column': col
            })

    if not entries:
        return None

    distinct_original_names = {e['original_name'] for e in entries}
    if len(distinct_original_names) == 1:
        return next(iter(distinct_original_names))

    distinct_match_names = {e['match_name'] for e in entries if e['match_name']}
    if len(distinct_match_names) == 1:
        best_entry = max(
            entries,
            key=lambda e: (
                -SOURCE_PRIORITY.get(e['source'], 999),
                -int(is_abbreviation(e['original_name'])),
                len(e['original_name'])
            )
        )
        return best_entry['original_name']

    graph = build_similarity_graph(entries, threshold=threshold)
    components = get_connected_components(graph)

    clusters = []
    for component in components:
        cluster_entries = [entries[i] for i in component]
        clusters.append(cluster_entries)

    winning_cluster = max(clusters, key=score_cluster)

    support_by_match_name = {}
    for entry in winning_cluster:
        support_by_match_name[entry['match_name']] = (
            support_by_match_name.get(entry['match_name'], 0) + 1
        )

    best_entry = max(
        winning_cluster,
        key=lambda e: score_candidate(
            e,
            support_by_match_name.get(e['match_name'], 1)
        )
    )

    return best_entry['original_name']


def resolve_name_fast(row, school_name_cols, threshold=90):
    values = []

    for col in school_name_cols:
        val = row.get(col, pd.NA)
        if pd.notna(val) and str(val).strip():
            values.append(str(val).strip())

    distinct_values = set(values)

    if not distinct_values:
        return None

    if len(distinct_values) == 1:
        return values[0]

    return get_best_school_name(row, school_name_cols, threshold=threshold)


def clean_final_school_name(name):
    """
    Post-selection cleanup only.
    This does not affect matching.
    """
    if pd.isna(name):
        return name

    name = str(name).strip()
    if not name:
        return name

    name_upper = name.upper()

    for pattern, replacement in ABBREVIATION_MAP.items():
        name_upper = re.sub(pattern, replacement, name_upper)

    name_upper = re.sub(r'\s+', ' ', name_upper).strip()

    return name_upper.title()


# -----------------------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------------------

def prepare_file(df, prefix):
    df = lowercase_columns(df)
    df = standardize_columns(df)
    df = standardize_ceeb_code(df)
    df = normalize_dataframe(df)
    df = add_prefix(df, prefix)
    return df


def main():
    # Load files
    file1, file2, file3, file4 = load_files()

    # Prepare files
    file1 = prepare_file(file1, 'SC_')
    file2 = prepare_file(file2, 'CAPPEX_')
    file3 = prepare_file(file3, 'PAPA_')
    file4 = prepare_file(file4, 'Enroll360_')

    # Debug CEEB code dtype
    print("CEEB code dtypes:")
    print(file1['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file1.columns else 'missing')
    print(file2['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file2.columns else 'missing')
    print(file3['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file3.columns else 'missing')
    print(file4['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file4.columns else 'missing')

    # Merge all files
    merged_df = file1.merge(file2, on='hs_ceeb_code', how='outer')
    merged_df = merged_df.merge(file3, on='hs_ceeb_code', how='outer')
    merged_df = merged_df.merge(file4, on='hs_ceeb_code', how='outer')

    print(f"\nMerged shape: {merged_df.shape}")
    print(f"Merged columns: {merged_df.columns.tolist()}")

    # School name columns
    school_name_cols = get_existing_columns(merged_df, [
        'SC_school_name',
        'Enroll360_school_name',
        'CAPPEX_school_name',
        'PAPA_school_name'
    ])

    print(f"\nSchool name columns: {school_name_cols}")

    # Resolve best school name
    merged_df['best_school_name'] = merged_df.apply(
        lambda row: resolve_name_fast(row, school_name_cols, threshold=90),
        axis=1
    )

    # Clean final school name after selection only
    merged_df['best_school_name_cleaned'] = merged_df['best_school_name'].apply(
        clean_final_school_name
    )

    # Optional audit flag
    merged_df['school_name_was_cleaned'] = (
        merged_df['best_school_name'].fillna('') !=
        merged_df['best_school_name_cleaned'].fillna('')
    )

    # Priority-based field selection
    address1_cols = get_existing_columns(merged_df, [
        'SC_address1',
        'Enroll360_address1',
        'CAPPEX_address1',
        'PAPA_address1'
    ])

    address2_cols = get_existing_columns(merged_df, [
        'SC_address2',
        'Enroll360_address2',
        'CAPPEX_address2',
        'PAPA_address2'
    ])

    city_cols = get_existing_columns(merged_df, [
        'SC_city',
        'Enroll360_city',
        'CAPPEX_city',
        'PAPA_city'
    ])

    state_cols = get_existing_columns(merged_df, [
        'SC_state',
        'Enroll360_state',
        'CAPPEX_state',
        'PAPA_state'
    ])

    zip_cols = get_existing_columns(merged_df, [
        'SC_zip',
        'Enroll360_zip',
        'CAPPEX_zip',
        'PAPA_zip'
    ])

    country_cols = get_existing_columns(merged_df, [
        'SC_country',
        'Enroll360_country',
        'CAPPEX_country',
        'PAPA_country'
    ])

    # Create final resolved fields
    merged_df['address1'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, address1_cols),
        axis=1
    )

    merged_df['address2'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, address2_cols),
        axis=1
    )

    merged_df['city'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, city_cols),
        axis=1
    )

    merged_df['state'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, state_cols),
        axis=1
    )

    merged_df['zip'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, zip_cols),
        axis=1
    )

    merged_df['country'] = merged_df.apply(
        lambda row: first_non_null_by_priority(row, country_cols),
        axis=1
    )

    # Final formatting
    merged_df['state'] = merged_df['state'].apply(lambda x: x.upper() if pd.notna(x) else x)
    merged_df['country'] = merged_df['country'].apply(lambda x: x.upper() if pd.notna(x) else x)

    # Final output columns
    final_columns = (
        ['hs_ceeb_code']
        + school_name_cols
        + [
            'best_school_name',
            'best_school_name_cleaned',
            'school_name_was_cleaned',
            'address1',
            'address2',
            'city',
            'state',
            'zip',
            'country'
        ]
    )

    result_df = merged_df[final_columns].copy()

    # Save outputs
    result_df.to_csv('merged_schools_new_1_12.csv', index=False)
    result_df.to_excel('merged_schools_new_1_12.xlsx', index=False, engine='openpyxl')

    print(f"\nMerged {len(result_df)} rows")
    print("\nFirst 10 rows:")
    print(result_df.head(10))


if __name__ == "__main__":
    main()