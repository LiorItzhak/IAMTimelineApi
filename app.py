import logging
import os

from flask import Flask, abort
from flask_caching import Cache
from dateutil.parser import parser
import pyodbc
from geopy.distance import distance
import pandas as pd
import random

app = Flask(__name__)
app.config.from_pyfile(f'{os.getenv("FLASK_ENV")}.conf.cfg')
app.logger.setLevel(logging.INFO)
cache = Cache(app)
date_parser = parser()


def exception_mapper(func):
    def inner_fun(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValueError, AssertionError) as e:
            return abort(400, str(e))

    return inner_fun


@app.route('/')
@cache.cached(timeout=60)  # 1 minute
def hello_world():
    random.randint(0, 10000)
    return f'Hello World! - random={random.randint(0, 10000)}'


@app.route('/route/<int:user_id>/<string:date>')
@cache.cached(timeout=60 * 60)  # 1 hour
@exception_mapper
def get_route(user_id, date):
    try:
        date = date_parser.parse(timestr=date).date()
    except Exception as e:
        raise ValueError(f"Cant parse date - {str(e)}")
    assert date <= date.today(), f"Cant use a future  date {date}"

    conn = pyodbc.connect(app.config["DATABASE_CONN_STR"])
    df = pd.read_sql(
        f"SELECT DateTime as timestamp,Latitude as lat, Longitude as lng FROM UserLocations  WHERE EmployeeSn={user_id} and CONVERT(Date, DateTime)='{date}' order by DateTime",
        conn)
    df = df.drop_duplicates(subset=['timestamp'])
    if df.shape[0] == 0:
        return abort(404)  # 404 Not Found
    df['index'] = df['timestamp']
    df = df.set_index('index')

    window = '10min'
    max_means_distance = 100

    mean_cols = ['lat', 'lng']
    df['count_b'] = df[mean_cols[0]].rolling(window).count()
    df['count_a'] = df[mean_cols[0]].iloc[::-1].rolling(window).count()
    df[[f'{col}_mean_b' for col in mean_cols]] = df[mean_cols].rolling(window).mean()
    df[[f'{col}_mean_a' for col in mean_cols]] = df[mean_cols].iloc[::-1].rolling(window).mean()

    df[['prv_lat_mean_b', 'prv_lng_mean_b', 'prv_lat_mean_a', 'prv_lng_mean_a']] = df.shift()[
        ['lat_mean_b', 'lng_mean_b', 'lat_mean_a', 'lng_mean_a']]

    df['means_distance_m'] = df.apply(
        lambda row: distance([row['lat_mean_b'], row['lng_mean_b']], [row['lat_mean_a'], row['lng_mean_a']]).m, axis=1)

    df['is_standing'] = df.means_distance_m < max_means_distance
    df['distance_between_means'] = df[1:].apply(
        lambda row: distance([row['prv_lat_mean_b'], row['prv_lng_mean_b']], [row['lat_mean_a'], row['lng_mean_a']]).m,
        axis=1)

    df['change_status'] = (df['is_standing'] - df['is_standing'].shift()) | (df['distance_between_means'] > 250)
    df.loc[df.index[0], 'change_status'] = 0

    df['status_id'] = (df.change_status != 0).groupby(level=0, sort=False).sum().cumsum()

    dff = df.groupby('status_id', sort=False)[['timestamp', 'lat', 'lng', 'is_standing', 'means_distance_m']] \
        .agg({'timestamp': ['count', 'max', 'min'],
              'is_standing': 'last',
              'lat': ['first', 'last', 'mean'],
              'lng': ['first', 'last', 'mean'],
              'means_distance_m': 'sum'})

    dff.columns = dff.columns.map('_'.join)

    dff['duration_s'] = dff.apply(lambda row: (row['timestamp_max'] - row['timestamp_min']).total_seconds(), axis=1)
    dff['index'] = dff['timestamp_min']
    dff = dff.set_index('index')
    dff = dff[['timestamp_min', 'duration_s', 'lat_mean', 'lng_mean']]
    dff = dff.rename(columns={"timestamp_min": "timestamp", "lat_mean": "lat", "lng_mean": "lng"})
    return dff.to_json(orient='records', date_format="iso")


if __name__ == '__main__':
    app.run(host='0.0.0.0')
