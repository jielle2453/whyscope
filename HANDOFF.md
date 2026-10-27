# 交接清單（2026-10-28 凌晨完成，給起床後的你）

截止：今天 17:00。倉庫：https://github.com/jielle2453/whyscope（目前私人）。

## 已完成、已實際跑過

| 項目 | 狀態 | 證據 |
|---|---|---|
| 原型主機服務（打字／語音提問 → 辨識 → 敏感過濾 → 檢索 → 童語生成 → 記錄） | 可跑，GPU 模式 | 六項驗證全過，見 docs/benchmarks.md |
| 孩子端網頁 /kid（按住說話、打字、可選開鏡頭、瀏覽器念出回答） | 可用 | 在內建瀏覽器開過，無錯誤 |
| 家長端網頁 /parent（本週、問題紀錄、家長小抄、孩子的世界、設定） | 可用 | 同上，有新增記憶與提問測試 |
| 知識庫 | 93 條（六主題各 15 加 3 條範例） | knowledge/entries/，格式檢查通過 |
| 家長小抄 | 10 類，含自傷類的 1925 與 1995 專線 | knowledge/cheats/ |
| 棄答測試集 | 120 題 | eval/abstention_set.jsonl |
| 棄答誤答率 | 門檻 0.55：準確率 91.7%，誤答 8、誤棄 2 | 我親自重跑一次，數字相同 |
| 延遲（RTX 4060，GPU 模式） | 文字提問約 1.5 s 全程；首句 7 ms；語音辨識約 0.1 s（首次 0.4–0.7 s） | docs/benchmarks.md |
| 文件 | README、architecture、models、safety、hardware、roadmap、benchmarks、spec | docs/ |
| 影片腳本 | 3 分鐘英文分鏡與錄製清單 | docs/video-script.md |

## 誠實標示

- 知識條目全部 AI 撰寫、未經人工審核；只核對過維基頁面存在與關鍵字，沒有逐句核對事實。`reviewed_by` 都是空的。
- 小抄的來源目前是機構首頁層級（衛福部、兒盟、UNICEF 等），要換成主題專頁。1925 與親子天下等網址抓不到，已排除。
- 棄答 91.7% 是樂觀值：檢索的覆蓋權重是對著同一份測試集調的。純餘弦相似度只有 55%。簡報裡要寫「初步」。
- 語音路徑用 Windows 合成語音測的，辨識成「刮牛」但檢索仍對到蝸牛。真人童聲完全沒測。
- 1.5B 模型約一半的輸出會發明事實，被接地檢查擋下後退回模板句。這正是設計要的，但代表生成層目前貢獻有限。
- 沒做：Hailo 模式、實體麥克風與鏡頭實測、視覺辨識真照片、llama-cpp（Windows 無現成套件）。
- 虛擬環境在 `C:\whyscope-venv`，因為倉庫路徑太長 CUDA 載不進來；run.ps1 會自動找到它。
- docs/benchmarks.md 末尾可能有兩段重複的棄答表（我重跑時又附加了一次），刪一段即可。

## 怎麼跑

```powershell
cd <倉庫資料夾>
scripts\run.ps1
```
開 http://localhost:8000/kid 與 http://localhost:8000/parent。手機連同一個 Wi-Fi 可用電腦的區網 IP 代替 localhost。

## 你起床要做的（依優先順序）

1. 跑起來，在 /kid 打「為什麼蝸牛有殼」、用麥克風講一次、問「為什麼人會死」看轉交、到 /parent 看紀錄。有問題貼錯誤給我。
2. 決定倉庫要不要改公開：`gh repo edit jielle2453/whyscope --visibility public --accept-visibility-change-consequences`
3. 英文簡報（還沒做，你說先不動）。簡報裡 GitHub 連結用上面的網址。
4. 照 docs/video-script.md 錄 3 分鐘影片，上傳 YouTube 設「知道連結者可觀看」。
5. 填團隊名稱、你的名字、聯絡方式；到報名頁繳交。

## 用量

全模型每週額度在開工時 83%，三個 Haiku 子代理後 84%；Sonnet 主程式子代理用量最大，最終數字我在最後一則訊息回報。
