import requests
from typing import Optional, Dict, List
import json

class BacklogAPIClient:
    def __init__(self, space_name: str, api_key: str):
        self.base_url = f"https://{space_name}.backlog.com/api/v2"
        self.api_key = api_key

    def _make_request(self, endpoint: str, method: str = 'GET', params: Dict = None) -> Dict:
        """APIリクエストを実行し、JSONレスポンスを返す"""
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        params['apiKey'] = self.api_key

        response = requests.request(method, url, params=params)
        response.raise_for_status()
        return response.json()

    # 1. 在席管理プロジェクトの課題取得
    def get_staff_issues(self, project_id: str = "550650") -> List[Dict]:
        """在席管理プロジェクトの課題一覧を取得"""
        params = {
            "projectId[]": project_id,
            "count": 3
        }
        json_response = self._make_request('/issues', params=params)
        
        # レスポンス例:
        # [
        #     {
        #         "id": 123457,
        #         "projectId": 550650,
        #         "issueKey": "STAFF-456",
        #         "summary": "山田 太郎",
        #         "status": {"id": 242353, "name": "不在"},
        #         "assignee": {"id": 12345, "name": "山田 太郎"}
        #     }
        # ]
        return json_response

    # 2. 請求管理プロジェクトの差し戻し課題取得
    def get_reverted_issues(self, project_id: str = "550648") -> List[Dict]:
        """差し戻し状態の課題一覧を取得"""
        params = {
            "projectId[]": project_id,
            "statusId[]": "262863",  # 差し戻しステータス
        }
        json_response = self._make_request('/issues', params=params)
        
        # レスポンス例:
        # [
        #     {
        #         "id": 123456,
        #         "issueKey": "BLG-123",
        #         "summary": "○○病院 - P123456",
        #         "status": {"id": 262863, "name": "差し戻し"}
        #     }
        # ]
        return json_response

    # 3. 医療機関情報の取得
    def get_hospital_issues(self, project_id: str = "569286") -> List[Dict]:
        """医療機関の課題一覧を取得"""
        params = {
            "projectId[]": project_id,
            "count": 100
        }
        json_response = self._make_request('/issues', params=params)
        
        # レスポンス例:
        # [
        #     {
        #         "id": 123458,
        #         "summary": "○○病院",
        #         "customFields": [
        #             {"name": "ID", "value": "hospital_user_123"},
        #             {"name": "ポーリング", "value": {"name": "有効"}}
        #         ]
        #     }
        # ]
        return json_response

    # 4. 課題の状態更新
    def update_issue_status(self, issue_id: str, status_id: str) -> Dict:
        """課題のステータスを更新"""
        params = {
            "statusId": status_id
        }
        json_response = self._make_request(
            f'/issues/{issue_id}',
            method='PATCH',
            params=params
        )
        
        # レスポンス例:
        # {
        #     "id": 123456,
        #     "status": {"id": 263209, "name": "差し戻し済み"}
        # }
        return json_response

# 使用例
def main():
    # クライアントの初期化
    client = BacklogAPIClient(
        space_name="oasis-inn",
        api_key="1vxPXhjOB1yfbswK4ShCFrCnAC0QfBBFWVqNJG5KFoDZYjreOuZ3qOCEUfRrZaVN"
    )

    try:
        # 1. 在席管理の課題を取得して処理
        staff_issues = client.get_staff_issues()
        for issue in staff_issues:
            print(f"スタッフ課題: {json.dumps(issue, indent=2, ensure_ascii=False)}")

        # # 2. 差し戻し課題を取得して処理
        # reverted_issues = client.get_reverted_issues()
        # for issue in reverted_issues:
        #     print(f"差し戻し課題: {json.dumps(issue, indent=2, ensure_ascii=False)}")

        # # 3. 医療機関情報を取得して処理
        # hospital_issues = client.get_hospital_issues()
        # for issue in hospital_issues:
        #     print(f"医療機関情報: {json.dumps(issue, indent=2, ensure_ascii=False)}")

        # # 4. 課題のステータスを更新
        # if reverted_issues:
        #     updated_issue = client.update_issue_status(
        #         reverted_issues[0]['id'],
        #         "263209"  # 差し戻し済みステータス
        #     )
        #     print(f"更新された課題: {json.dumps(updated_issue, indent=2, ensure_ascii=False)}")

    except requests.exceptions.RequestException as e:
        print(f"APIリクエストエラー: {e}")
        if hasattr(e, 'response'):
            print(f"エラーレスポンス: {e.response.text}")
    except Exception as e:
        print(f"予期せぬエラー: {e}")

if __name__ == "__main__":
    main()