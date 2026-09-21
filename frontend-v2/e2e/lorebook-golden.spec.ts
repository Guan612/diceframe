import { expect, test } from './fixtures'

/**
 * Lorebook Golden — 真实链路，不 mock 任何 API。
 *
 *   Browser → real frontend → real backend → real SQLite → real migration
 *           → real resolver → real matcher/retrieval
 *
 * 数据来自 scripts/prepare_e2e_data.py 落的**真 v4 老库**（lorebook.db 停在 schema
 * v4），服务器启动时跑真实 migration。因此这条用例同时验收：
 *
 *   - v4 老库 → startup migration → primary world book 可见
 *   - Book 产品流：create / rename / enable-disable / delete / binding 管理
 *   - Import：detect → preview → 选择导入目标与 binding → confirm → persist
 *   - 真实 matcher：keyword → recursion → visibility（GM 看得到密档、玩家看不到）
 *   - export → reimport 往返
 *
 * 与 lorebook-mocked-flow.spec.ts 的分工：那条只证明 UI 对自己
 * mock 的忠诚度），这条是唯一的 Golden。
 */

// 与 scripts/prepare_e2e_data.py 的 E2E_LORE_WORLD_ID / E2E_LORE_GAME_KEY 一致。
const LORE_WORLD_ID = 'e2e_lore_golden'
const LORE_GAME_KEY = 'web|e2e-lore-golden|web_bot'

/**
 * 导入 fixture 用 lorebook_v3：它能带 book 级 recursive_scanning，因此 recursion
 * 与 secondary filter 都能在真实 import → resolver → matcher 链上被验收，而不是
 * 靠测试自己断言一个没人执行过的配置。
 */
const IMPORT_FIXTURE = JSON.stringify({
  spec: 'lorebook_v3',
  data: {
    lorebook: {
      name: 'Golden Imported Book',
      recursive_scanning: true,
      entries: [
        { id: 'imp-bell', name: '潮汐钟', keys: ['潮汐钟'], content: '潮汐钟的钟摆连着沉船账本。' },
        { id: 'imp-ledger', name: '沉船账本', keys: ['沉船账本'], content: '账本记着走私航线。' },
        {
          id: 'imp-watch', name: '巡夜人', keys: ['潮汐钟'], secondary_keys: ['满月'],
          selective_logic: 'and_all', content: '满月之夜钟声会引来巡夜人。',
        },
      ],
    },
  },
})

test.describe('Lorebook Golden (real chain)', () => {
  test.skip(({ browserName }) => browserName !== 'chromium', 'Golden runs on the CI browser only')

  test('migrated v4 lore, book management, binding-aware import and real activation', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', 'Golden uses the desktop inspector layout')

    const failures: string[] = []
    page.on('response', response => {
      const url = response.url()
      if (url.includes('/api/') && response.status() >= 500) failures.push(`${response.status()} ${url}`)
    })

    // Activation Inspector 走真实 retriever，需要一个绑定到该世界的存档。
    await page.addInitScript(gameKey => {
      localStorage.setItem('lore_inspector_open', '1')
      localStorage.setItem('currentGame', gameKey)
    }, LORE_GAME_KEY)

    // ---- 1. v4 老库经真实 migration 后应当出现在产品界面上 -------------------
    await page.goto('/#/lorebook')
    await expect(page.locator('.lorebook-page')).toBeVisible()

    const worldSelect = page.locator('.lore-world-bar select').nth(1)
    await worldSelect.selectOption(LORE_WORLD_ID)

    const sidebar = page.locator('.lorebook-sidebar')
    await expect(sidebar.locator('.lorebook-sidebar__item').first()).toBeVisible()
    // 迁移产物：主世界书存在，并标成 Primary + 当前世界。
    const primaryItem = sidebar.locator('.lorebook-sidebar__item', { hasText: 'Primary' }).first()
    await expect(primaryItem).toContainText('Primary')
    await expect(primaryItem).toContainText('当前世界')
    // 真实条目来自迁移后的 SQLite，不是测试 fabricate 的 JSON。
    await expect(page.locator('.lore-row', { hasText: '旧城门' }).first()).toBeVisible()

    // ---- 2. 真实 matcher：keyword → recursion，GM 视角看得到密档 ------------
    const activationInput = page.locator('.lore-activation-input')
    await activationInput.fill('我去旧城门看看')
    await page.getByRole('button', { name: 'Preview activation', exact: true }).click()
    const trace = page.locator('.lore-activation-trace')
    await expect(trace).toContainText('legacy-gate')
    await expect(trace).toContainText('legacy-secret')

    // ---- 3. 玩家视角：hidden 条目连一行都不该出现 ---------------------------
    await page.getByRole('button', { name: '全队', exact: true }).click()
    await page.getByRole('button', { name: 'Preview activation', exact: true }).click()
    await expect(trace).toContainText('legacy-gate')
    await expect(trace).not.toContainText('legacy-secret')
    await page.getByRole('button', { name: 'GM 全知', exact: true }).click()

    // ---- 4. Book 产品流：新建 → 重命名 → 停用/启用 -------------------------
    page.once('dialog', dialog => dialog.accept('Golden Extra Book'))
    await sidebar.getByRole('button', { name: '新建世界书', exact: true }).click()
    const extraRow = sidebar.locator('.lorebook-sidebar__row', { hasText: 'Golden Extra Book' })
    await expect(extraRow).toBeVisible()

    page.once('dialog', dialog => dialog.accept('Golden Renamed Book'))
    await extraRow.getByRole('button', { name: /^重命名/ }).click()
    const renamedRow = sidebar.locator('.lorebook-sidebar__row', { hasText: 'Golden Renamed Book' })
    await expect(renamedRow).toBeVisible()

    await renamedRow.getByRole('button', { name: /^停用/ }).click()
    await expect(renamedRow.locator('.lorebook-sidebar__item')).toContainText('已停用')
    await renamedRow.getByRole('button', { name: /^启用/ }).click()
    await expect(renamedRow.locator('.lorebook-sidebar__item')).toContainText('启用中')

    // ---- 5. binding 管理：新增一条 world binding 并解除 --------------------
    await renamedRow.getByRole('button', { name: /^绑定/ }).click()
    const bindingsDialog = page.getByRole('dialog', { name: 'Manage bindings' })
    await expect(bindingsDialog).toBeVisible()
    await bindingsDialog.getByRole('button', { name: '新增', exact: true }).click()
    await expect(bindingsDialog.locator('.lore-binding-row')).toHaveCount(1)
    await expect(bindingsDialog.locator('.lore-binding-row')).toContainText('world')
    await bindingsDialog.getByRole('button', { name: /^解除绑定/ }).click()
    await expect(bindingsDialog.locator('.lore-binding-row')).toHaveCount(0)
    await bindingsDialog.getByRole('button', { name: '关闭', exact: true }).click()

    // ---- 6. Import：detect → preview → 选目标/binding → confirm → persist --
    await page.locator('input[type=file]').setInputFiles({
      name: 'golden-import.json', mimeType: 'application/json', buffer: Buffer.from(IMPORT_FIXTURE),
    })
    const importDialog = page.getByRole('dialog', { name: 'Import lorebook' })
    // 格式由真实后端 detect，不是前端猜的。
    await expect(importDialog).toContainText('lorebook_v3')
    // 默认是「新建独立 Book」，不会隐式写进主世界书。
    await expect(importDialog.locator('.lore-import-dialog__primary-warning')).toHaveCount(0)
    await importDialog.locator('.lore-import-dialog__binding input[value=world]').check()
    await importDialog.getByRole('button', { name: 'Import', exact: true }).click()
    await expect(importDialog).toBeHidden()

    // 导入结果来自真实 SQLite：新 Book 出现，条目可读。
    await expect(page.locator('.lore-row', { hasText: '潮汐钟' }).first()).toBeVisible()

    // ---- 6b. 真实 matcher：recursion + secondary filter ---------------------
    // 「潮汐钟」直接命中，其正文提到「沉船账本」→ recursion 带出子条目。
    await activationInput.fill('我敲响潮汐钟')
    await page.getByRole('button', { name: 'Preview activation', exact: true }).click()
    await expect(trace).toContainText('recursive')
    // trace 会列出作用域内**每一条**条目（含 omitted），所以要数真正进入结果的行。
    // 存档的 scene 本身也是检索锚点，因此这里只断言「多了一条」，不钉死绝对值。
    const included = trace.locator('li', { hasText: 'included' })
    const withoutMoon = await included.count()
    expect(withoutMoon).toBeGreaterThan(0)
    // 「巡夜人」的 secondary key 是「满月」：只有提到满月才应额外激活它。
    await activationInput.fill('满月之夜我敲响潮汐钟')
    await page.getByRole('button', { name: 'Preview activation', exact: true }).click()
    await expect(included).toHaveCount(withoutMoon + 1)

    // ---- 7. 导入主世界书必须显式提示（不能隐式发生）------------------------
    await page.locator('input[type=file]').setInputFiles({
      name: 'golden-import-2.json', mimeType: 'application/json', buffer: Buffer.from(IMPORT_FIXTURE),
    })
    const secondDialog = page.getByRole('dialog', { name: 'Import lorebook' })
    await secondDialog.locator('.lore-import-dialog__target input[value=existing]').check()
    await secondDialog.locator('.lore-import-dialog__book').selectOption(`world:${LORE_WORLD_ID}`)
    await expect(secondDialog.locator('.lore-import-dialog__primary-warning'))
      .toContainText('将导入当前世界主世界书')
    await secondDialog.getByRole('button', { name: 'Cancel', exact: true }).click()

    // ---- 8. export → reimport 往返（真实 exporter / importer）-------------
    const download = page.waitForEvent('download')
    await sidebar.getByRole('button', { name: '导出', exact: true }).click()
    const exported = await download
    const stream = await exported.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const exportedJson = Buffer.concat(chunks).toString('utf-8')
    expect(JSON.parse(exportedJson)).toBeTruthy()

    await page.locator('input[type=file]').setInputFiles({
      name: 'golden-roundtrip.json', mimeType: 'application/json', buffer: Buffer.from(exportedJson),
    })
    const roundTripDialog = page.getByRole('dialog', { name: 'Import lorebook' })
    await expect(roundTripDialog).toContainText('lorebook_v3')
    await roundTripDialog.locator('.lore-import-dialog__binding input[value=none]').check()
    await roundTripDialog.getByRole('button', { name: 'Import', exact: true }).click()
    await expect(roundTripDialog).toBeHidden()

    // ---- 9. 删除非主世界书；主世界书没有删除入口 --------------------------
    const primaryRow = sidebar.locator('.lorebook-sidebar__row', { hasText: 'Primary' }).first()
    await expect(primaryRow.getByRole('button', { name: /^删除/ })).toHaveCount(0)

    await renamedRow.getByRole('button', { name: /^删除/ }).click()
    await page.getByRole('button', { name: '删除世界书', exact: true }).click()
    await expect(sidebar.locator('.lorebook-sidebar__row', { hasText: 'Golden Renamed Book' })).toHaveCount(0)

    expect(failures, `backend 5xx during the golden run:\n${failures.join('\n')}`).toEqual([])
  })
})
