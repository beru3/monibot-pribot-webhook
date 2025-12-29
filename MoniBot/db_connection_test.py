#!/usr/bin/env python3
# db_connection_test.py - データベース接続テストスクリプト

import os
import sys
import configparser
import mysql.connector
from mysql.connector import Error

# プロジェクトルートへのパスを追加
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

def load_config(filename='config.ini'):
    """設定ファイルを読み込む"""
    config = configparser.ConfigParser()
    config_path = os.path.join(project_root, 'config', filename)
    try:
        config.read(config_path, encoding='utf-8')
        db_config = {
            'host': config['mysql']['host'],
            'user': config['mysql']['user'],
            'password': config['mysql']['password'],
            'database': config['mysql']['database']
        }
        return config, db_config
    except Exception as e:
        print(f"❌ 設定ファイルの読み込みに失敗しました: {e}")
        return None, None

def test_database_connection():
    """データベース接続をテストする"""
    print("=" * 60)
    print("データベース接続テスト開始")
    print("=" * 60)
    
    # 設定読み込み
    config, db_config = load_config()
    if not db_config:
        return False
    
    print(f"📋 接続設定:")
    print(f"   ホスト: {db_config['host']}")
    print(f"   ユーザー: {db_config['user']}")
    print(f"   データベース: {db_config['database']}")
    print()
    
    try:
        # データベース接続
        print("🔗 データベースに接続中...")
        connection = mysql.connector.connect(**db_config)
        
        if connection.is_connected():
            db_info = connection.get_server_info()
            print(f"✅ データベース接続成功！")
            print(f"   MySQL サーバーバージョン: {db_info}")
            
            cursor = connection.cursor()
            
            # データベース情報の確認
            cursor.execute("SELECT DATABASE();")
            database_name = cursor.fetchone()
            print(f"   現在のデータベース: {database_name[0]}")
            
            # テーブル一覧の確認
            print("\n📊 テーブル一覧:")
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            
            if tables:
                for table in tables:
                    print(f"   - {table[0]}")
                
                # 各テーブルのレコード数を確認
                print("\n📈 各テーブルのレコード数:")
                for table in tables:
                    table_name = table[0]
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                    count = cursor.fetchone()[0]
                    print(f"   {table_name}: {count:,} 件")
                
            else:
                print("   テーブルが見つかりませんでした")
            
            # ストアドプロシージャの確認
            print("\n🔧 ストアドプロシージャ一覧:")
            cursor.execute("SHOW PROCEDURE STATUS WHERE Db = %s;", (db_config['database'],))
            procedures = cursor.fetchall()
            
            if procedures:
                for proc in procedures:
                    print(f"   - {proc[1]}")  # proc[1] がプロシージャ名
            else:
                print("   ストアドプロシージャが見つかりませんでした")
            
            print("\n🎉 データベース接続テスト完了！")
            return True
            
    except Error as e:
        print(f"❌ データベース接続エラー: {e}")
        return False
        
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("📤 データベース接続を閉じました")

def test_backlog_settings():
    """Backlog設定の確認"""
    print("\n" + "=" * 60)
    print("Backlog設定確認")
    print("=" * 60)
    
    config, _ = load_config()
    if not config:
        return False
    
    try:
        backlog_settings = dict(config['backlog'])
        print("🎯 Backlog設定:")
        for key, value in backlog_settings.items():
            # API キーは一部マスク
            if key == 'api_key':
                masked_value = value[:8] + "*" * (len(value) - 16) + value[-8:] if len(value) > 16 else "*" * len(value)
                print(f"   {key}: {masked_value}")
            else:
                print(f"   {key}: {value}")
        
        return True
        
    except KeyError as e:
        print(f"❌ Backlog設定にエラーがあります: {e}")
        return False

if __name__ == "__main__":
    print("🚀 医療システム環境テスト")
    print(f"作業ディレクトリ: {os.getcwd()}")
    print()
    
    # データベース接続テスト
    db_success = test_database_connection()
    
    # Backlog設定テスト
    backlog_success = test_backlog_settings()
    
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    print(f"データベース接続: {'✅ 成功' if db_success else '❌ 失敗'}")
    print(f"Backlog設定: {'✅ OK' if backlog_success else '❌ エラー'}")
    
    if db_success and backlog_success:
        print("\n🎉 全ての基本設定が正常です！システム起動の準備ができました。")
        sys.exit(0)
    else:
        print("\n⚠️  設定に問題があります。修正してから再度テストしてください。")
        sys.exit(1)