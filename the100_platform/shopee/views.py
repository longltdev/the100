from django.shortcuts import render
import hmac
import json
import time
import requests
import hashlib
import logging
from django.http import JsonResponse
from django.conf import settings
from .models import ShopAuth, ShopAccessToken
from categories.models import Category
from datetime import datetime, timedelta, timezone

logging.basicConfig(format='%(name)s - %(levelname)s - %(message)s')


# Create your views here.

def get_sign_authentication(partner_id, partner_key, path, timest):
    tmp_base_string = "%s%s%s" % (partner_id, path, timest)
    base_string = tmp_base_string.encode()
    return hmac.new(partner_key, base_string, hashlib.sha256).hexdigest()


def get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id):
    tmp_base_string = "%s%s%s%s%s" % (partner_id, path, timest, access_token, shop_id)
    base_string = tmp_base_string.encode()
    return hmac.new(partner_key, base_string, hashlib.sha256).hexdigest()


def check_expired_access_token(request):
    # Check if access_token is expired, if not, call refresh_token to get latest access_token
    shop_access_token = ShopAccessToken.objects.get(user=request.user)
    print('====', shop_access_token)
    shop_auth_obj = ShopAuth.objects.get(user=request.user)
    print('====', shop_auth_obj)
    current_datetime = datetime.now(timezone.utc)
    print('Current datetime: %s' % current_datetime)
    print('DB datetime: %s ' % shop_access_token.updated_at)
    # time_difference = (current_datetime - shop_access_token.updated_at) / timedelta(hours=1)
    duration = current_datetime - shop_access_token.updated_at
    duration_in_s = duration.total_seconds()
    hours = divmod(duration_in_s, 3600)[0]
    print(hours)
    if hours > 4:
        print('refresh token')
        print(shop_auth_obj.shop_id, shop_access_token.refresh_token)
        new_access_token, new_refresh_token = get_refresh_token(shop_auth_obj.shop_id, shop_access_token.refresh_token)
        print(new_access_token, new_refresh_token)
        shop_access_token.access_token = new_access_token
        shop_access_token.refresh_token = new_refresh_token
        shop_access_token.updated_at = current_datetime
        shop_access_token.save()
        return new_access_token, new_refresh_token
    return shop_access_token.access_token, None


def post_request(url, body):
    headers = {"Content-Type": "application/json"}
    return requests.post(url, json=body, headers=headers).json()


def shop_auth(request):
    if request.method == 'POST':
        timest = int(time.time())
        host = settings.SHOP_AUTH_HOST
        path = settings.SHOP_AUTH_PATH
        redirect_url = settings.SHOP_AUTH_REDIRECT_URL
        partner_id = settings.PARTNER_ID
        partner_key = settings.LIVE_KEY
        sign = get_sign_authentication(partner_id, partner_key, path, timest)
        ##generate api
        url = f'{host}{path}?partner_id={partner_id}&timestamp={timest}&sign={sign}&redirect={redirect_url}'
        print(url)
        return JsonResponse({'url': url})


def get_token_shop_level(code, shop_id):
    partner_id = settings.PARTNER_ID
    partner_key = settings.LIVE_KEY
    timest = int(time.time())
    host = settings.SHOP_AUTH_HOST
    path = settings.TOKEN_GET_PATH
    body = {"code": code, "shop_id": int(shop_id), "partner_id": partner_id}
    sign = get_sign_authentication(partner_id, partner_key, path, timest)
    url = f'{host}{path}?partner_id={partner_id}&timestamp={timest}&sign={sign}'
    print(url)
    resp = post_request(url, body)
    print('***************', resp)
    access_token = resp.get("access_token")
    new_refresh_token = resp.get("refresh_token")
    return access_token, new_refresh_token


def get_refresh_token(shop_id, refresh_token):
    partner_id = settings.PARTNER_ID
    partner_key = settings.LIVE_KEY
    timest = int(time.time())
    host = settings.SHOP_AUTH_HOST
    path = settings.REFRESH_ACCESS_TOKEN_PATH
    body = {"shop_id": shop_id, "refresh_token": refresh_token, "partner_id": partner_id}
    sign = get_sign_authentication(partner_id, partner_key, path, timest)
    url = f'{host}{path}?partner_id={partner_id}&timestamp={timest}&sign={sign}'
    print(url)
    print(body)
    resp = post_request(url, body)
    print('***************', resp)
    access_token = resp.get("access_token")
    new_refresh_token = resp.get("refresh_token")
    return access_token, new_refresh_token


def get_categories(request):
    if request.user.is_authenticated:
        partner_id = settings.PARTNER_ID
        partner_key = settings.LIVE_KEY
        shop_id = ShopAuth.objects.get(user=request.user).shop_id
        access_token, _ = check_expired_access_token(request)
        timest = int(time.time())
        host = settings.SHOP_AUTH_HOST
        path = settings.LIST_CATEGORIES
        # body = {"shop_id": shop_id, "access_token": access_token, "partner_id": partner_id}
        sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
        url = f'{host}{path}?access_token={access_token}&language=vi&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
        print(url)
        payload = {}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
        # resp = requests.get(url=url, headers=headers)
        resp = requests.get(url, headers=headers).json()
        return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def push_categories(request):
    if request.user.is_authenticated:
        data = get_categories(request)
        category_list = json.loads(data.content)['data']['response']['category_list']
        list_category_model = []
        for category in category_list:
            list_category_model.append(
                Category(id=category['category_id'], parent_category_id=category['parent_category_id'],
                         original_category_name=category['original_category_name'],
                         display_category_name=category['display_category_name'],
                         has_children=category['has_children']))
        Category.objects.bulk_create(list_category_model)
        return JsonResponse({'message': 'Done'})
    return {'error': 'Not authenticated'}


def get_attributes(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            # print(category_id)
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            # access_token = ShopAccessToken.objects.get(user=request.user).access_token
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_ATTRIBUTES
            # body = {"shop_id": shop_id, "access_token": access_token, "partner_id": partner_id}
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&language=vi&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def get_brands(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_BRANDS
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&language=vi&offset=0&page_size=10&status=1&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def get_dts_limit(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_DTS_LIMIT
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def get_size_chart(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_SIZE_CHART
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def get_item_limit(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_ITEM_LIMIT
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}


def get_channel_list(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            category_id = json.loads(request.body.decode('utf-8')).get('categoryId')
            partner_id = settings.PARTNER_ID
            partner_key = settings.LIVE_KEY
            shop_id = ShopAuth.objects.get(user=request.user).shop_id
            access_token, _ = check_expired_access_token(request)
            timest = int(time.time())
            host = settings.SHOP_AUTH_HOST
            path = settings.LIST_CHANNEL
            sign = get_sign_with_access_token(partner_id, partner_key, path, timest, access_token, shop_id)
            url = f'{host}{path}?access_token={access_token}&category_id={category_id}&partner_id={partner_id}&shop_id={shop_id}&timestamp={timest}&sign={sign}'
            print(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}
            # resp = requests.get(url=url, headers=headers)
            resp = requests.get(url, headers=headers).json()
            return JsonResponse({'data': resp})
    return {'error': 'Not authenticated'}
