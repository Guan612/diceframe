import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { i18n } from '../src/i18n'
import GmToolbar from '../src/components/play/GmToolbar.vue'

function findSelectWithOption(wrapper: VueWrapper, value: string) {
  const select = wrapper.findAll('select').find(
    item => Array.from(item.element.options).some(option => option.value === value),
  )
  expect(select, `应找到含选项 ${value} 的下拉框`).toBeTruthy()
  return select!
}

describe('GmToolbar',()=>{
  it('emits one recap request and exposes its busy state',async()=>{
    i18n.global.locale.value = 'en'
    const wrapper=mount(GmToolbar,{global:{plugins:[i18n]},props:{
      detail:{game_key:'web|room|bot',round_number:4},
      players:[],
      isGm:true,
      recapBusy:false,
    }})

    const button=wrapper.findAll('button').find(item => item.text().includes('Story Recap'))!
    expect(button).toBeTruthy()
    await button.trigger('click')
    expect(wrapper.emitted('recap')).toHaveLength(1)

    await wrapper.setProps({recapBusy:true})
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toContain('Generating')
  })

  it('lets a GM change the saved narrative perspective for any ruleset',async()=>{
    i18n.global.locale.value = 'zh-CN'
    const wrapper=mount(GmToolbar,{global:{plugins:[i18n]},props:{
      detail:{
        game_key:'web|room|bot',
        narrative_perspective:'immersive',
        ruleset_runtime:{
          id:'core:legacy',version:1,requested_minimum_version:1,
          capabilities:{
            experience_profile:'classic',character_builder:'legacy',
            character_lifecycle:'legacy',authoritative_intents:false,
            deterministic_combat:false,versioned_state:false,session_zero:false,
            tutorial_coach:false,narrative_turns:true,
          },
        },
      },
      players:[],
      isGm:true,
    }})

    const select=findSelectWithOption(wrapper,'immersive')
    expect((select.element as HTMLSelectElement).value).toBe('immersive')
    await select.setValue('third_person')
    expect(wrapper.emitted('narrative-perspective')).toEqual([['third_person']])
  })

  it('lets a D&D GM configure advancement and grant one entitlement',async()=>{
    i18n.global.locale.value = 'zh-CN'
    const wrapper=mount(GmToolbar,{global:{plugins:[i18n]},props:{
      detail:{
        game_key:'web|room|bot',
        ruleset_runtime:{
          id:'core:dnd2024',version:1,requested_minimum_version:1,
          capabilities:{
            experience_profile:'advanced',character_builder:'professional',
            character_lifecycle:'rules_aware',authoritative_intents:true,
            deterministic_combat:true,versioned_state:true,session_zero:true,
            tutorial_coach:false,narrative_turns:true,
          },
        },
        advancement:{
          mode:'milestone',authority:'gm',
          players:[{user_id:'hero',character_name:'阿刁',level:1,xp:0,next_level_xp:300,entitled:false,target_level:0,source:''}],
        },
      },
      players:[],
      isGm:true,
    }})

    const modeSelect=findSelectWithOption(wrapper,'xp')
    await modeSelect.setValue('xp')
    expect(wrapper.emitted('advancement-control')?.[0]).toEqual([{
      action:'configure',mode:'xp',authority:'gm',
    }])

    // 升级区域唯一的按钮是玩家行的授予按钮
    const section=(modeSelect.element.closest('details') as HTMLElement)
    const grantButton=Array.from(section.querySelectorAll('button'))[0] as HTMLButtonElement
    grantButton.click()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('advancement-control')?.[1]).toEqual([{
      action:'grant',user_id:'hero',
    }])
  })
})
