import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# Securely pull the RapidAPI key from Streamlit secrets
RAPIDAPI_KEY = st.secrets["RAPIDAPI"]["key"]
RAPIDAPI_HOST = 'zillow-com4.p.rapidapi.com'

def extract_properties_from_schema(raw_data, include_days_on_market=False):
    properties = []
    data_section = raw_data.get('data', [])

    if not isinstance(data_section, list):
        st.warning("Unexpected data format: 'data' is not a list")
        return properties

    for item in data_section:
        prop_data = item.get('property')
        if not prop_data:
            continue

        address_info = prop_data.get('address', {})
        sold_timestamp = prop_data.get('lastSoldDate')
        sold_date = datetime.fromtimestamp(sold_timestamp / 1000) if sold_timestamp else None

        latitude = prop_data.get('location', {}).get('latitude')
        longitude = prop_data.get('location', {}).get('longitude')
        google_maps_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}" if latitude and longitude else ""
        short_map_link = f"<a href='{google_maps_link}' target='_blank'>Map Link</a>" if google_maps_link else ""

        price = prop_data.get('price', {}).get('value') or prop_data.get('hdpView', {}).get('price')
        sqft = prop_data.get('livingArea')
        price_per_sqft = (price / sqft) if price and sqft else None
        zestimate = prop_data.get('estimates', {}).get('zestimate')
        discount_vs_zestimate = f"{((zestimate - price) / zestimate * 100):.1f}%" if price and zestimate else None

        is_preforeclosure = prop_data.get('isPreforeclosureAuction', False)
        is_preforeclosure_str = "Yes" if is_preforeclosure else "No"

        zpid = prop_data.get('zpid')
        zillow_link = f"https://www.zillow.com/homedetails/{zpid}_zpid/" if zpid else ""
        short_zillow_link = f"<a href='{zillow_link}' target='_blank'>Zillow Listing</a>" if zillow_link else ""
        thumbnail = prop_data.get('media', {}).get('propertyPhotoLinks', {}).get('highResolutionLink', '')

        record = {
            'Sold Date': sold_date,
            'Address': f"{address_info.get('streetAddress')}, {address_info.get('city')}, {address_info.get('state')} {address_info.get('zipcode')}",
            'Price': f"${price:,.2f}" if price else None,
            'Raw Price': price,
            'Price per SqFt': price_per_sqft,
            'Beds': int(prop_data.get('bedrooms')) if prop_data.get('bedrooms') else None,
            'Baths': prop_data.get('bathrooms'),
            'SqFt': sqft,
            'Year Built': prop_data.get('yearBuilt'),
            'Lot Size (sqft)': prop_data.get('lotSizeWithUnit', {}).get('lotSize'),
            'Days on Market': prop_data.get('daysOnZillow') if include_days_on_market else None,
            'Preforeclosure Auction': is_preforeclosure_str,
            'Map Link': short_map_link,
            'Zillow Link': short_zillow_link,
            'Thumbnail': f"<a href='{zillow_link}' target='_blank'><img src='{thumbnail}' width='100'></a>" if thumbnail else "",
            'Discount vs Zestimate': discount_vs_zestimate
        }

        properties.append(record)

    return properties

def fetch_properties(endpoint, zip_code):
    url = f"https://zillow-com4.p.rapidapi.com/v2/properties/{endpoint}"
    payload = {"location": zip_code}
    headers = {
        'x-rapidapi-key': RAPIDAPI_KEY,
        'x-rapidapi-host': RAPIDAPI_HOST,
        'Content-Type': 'application/json'
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise Exception(f"API call failed with status code {response.status_code}: {response.text}")
    return response.json()

def display_properties(properties, title, is_active=False):
    st.write(f"### {title}")
    df = pd.DataFrame(properties)

    columns = [col for col in df.columns if col != 'Days on Market' and col != 'Discount vs Zestimate']
    if 'Days on Market' in df.columns:
        columns.insert(8, 'Days on Market')
    if 'Discount vs Zestimate' in df.columns:
        columns.append('Discount vs Zestimate')
    df = df[columns]

    df_numeric = df.copy()
    df_numeric['Price per SqFt'] = pd.to_numeric(df_numeric['Price per SqFt'], errors='coerce')

    price_per_sqft_series = df_numeric['Price per SqFt'].dropna()
    if not price_per_sqft_series.empty:
        avg_price_per_sqft = price_per_sqft_series.mean()
        min_price_per_sqft = price_per_sqft_series.min()
        max_price_per_sqft = price_per_sqft_series.max()
        median_price_per_sqft = price_per_sqft_series.median()
        lower_quantile = price_per_sqft_series.quantile(0.2)
        upper_quantile = price_per_sqft_series.quantile(0.8)
        middle_80_series = price_per_sqft_series[(price_per_sqft_series >= lower_quantile) & (price_per_sqft_series <= upper_quantile)]
        avg_middle_80 = middle_80_series.mean() if not middle_80_series.empty else None

        if is_active and avg_middle_80:
            df['Discount vs 80%'] = df_numeric['Price per SqFt'].apply(
                lambda x: f"{((avg_middle_80 - x) / avg_middle_80 * 100):.1f}%" if x and avg_middle_80 else None
            )

        stats_lines = [
            f"- Average: ${avg_price_per_sqft:,.2f}",
            f"- Minimum: ${min_price_per_sqft:,.2f}",
            f"- Maximum: ${max_price_per_sqft:,.2f}",
            f"- Median: ${median_price_per_sqft:,.2f}",
            f"- Middle 80% Range (20%-80%): ${lower_quantile:,.2f}-${upper_quantile:,.2f}",
        ]
        if avg_middle_80 is not None:
            stats_lines.append(f"- Average (Middle 80% Only): ${avg_middle_80:,.2f}")

        st.markdown(f"### Price per SqFt Stats:")
        for line in stats_lines:
            st.markdown(f"<span style='font-size:90%'>{line}</span>", unsafe_allow_html=True)

        stats_row = pd.DataFrame({
            'Address': ['STATISTICS'],
            'Price': [None],
            'Price per SqFt': [
                f"Avg: ${avg_price_per_sqft:,.2f}, Min: ${min_price_per_sqft:,.2f}, Max: ${max_price_per_sqft:,.2f}, Median: ${median_price_per_sqft:,.2f}, Middle 80% Range: ${lower_quantile:,.2f}-${upper_quantile:,.2f}, Avg Middle 80%: ${avg_middle_80:,.2f}" if avg_middle_80 is not None else ""
            ]
        })
        export_df = pd.concat([df, stats_row], ignore_index=True)
    else:
        st.write("No valid Price per SqFt data to calculate statistics.")
        export_df = df

    display_df = df.drop(columns=['Raw Price']) if 'Raw Price' in df.columns else df
    st.write(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
    csv = export_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        f"Download {title} CSV",
        csv,
        f"{title.replace(' ', '_').lower()}.csv",
        "text/csv",
        key=f'download-{title.replace(" ", "-").lower()}'
    )

def main():
    st.title("Real Estate Properties Finder")

    zip_code = st.text_input("Enter ZIP Code", "32208")

    today = datetime.today().date()
    default_start = today - timedelta(days=730)
    start_date = st.date_input("Start Sold Date", default_start)
    end_date = st.date_input("End Sold Date", today)

    show_debug = st.checkbox("Show raw API response (debug)")

    if st.button("Fetch Sold Properties"):
        try:
            raw_data = fetch_properties("search-sold", zip_code)
            if show_debug:
                st.subheader("Full Raw API Data")
                st.json(raw_data)

            properties = extract_properties_from_schema(raw_data)
            st.write(f"Found {len(properties)} sold properties in API response.")

            if properties:
                df = pd.DataFrame(properties)
                df['Sold Date'] = pd.to_datetime(df['Sold Date'])
                mask = (df['Sold Date'].dt.date >= start_date) & (df['Sold Date'].dt.date <= end_date)
                filtered_df = df.loc[mask]
                display_properties(filtered_df, f"Sold Properties in {zip_code} from {start_date} to {end_date}")
            else:
                st.warning("No sold properties found.")

        except Exception as e:
            st.error(f"Error: {e}")

    if st.button("Fetch Active Listings"):
        try:
            raw_data = fetch_properties("search-for-sale", zip_code)
            if show_debug:
                st.subheader("Full Raw API Data")
                st.json(raw_data)

            properties = extract_properties_from_schema(raw_data, include_days_on_market=True)
            st.write(f"Found {len(properties)} active listings in API response.")

            if properties:
                display_properties(properties, f"Active Listings in {zip_code}", is_active=True)
            else:
                st.warning("No active listings found.")

        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
