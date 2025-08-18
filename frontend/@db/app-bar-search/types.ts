// @db/app-bar-search/types.ts
export interface SearchResults {
  id: string
  title: string
  url?: string
  icon?: string
  category?: string
}

export interface SearchItem extends SearchResults {
  children?: SearchResults[]
}

export interface SearchCategory {
  category: string
  items: SearchResults[]
}
