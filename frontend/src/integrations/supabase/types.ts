export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.1"
  }
  public: {
    Tables: {
      classes: {
        Row: {
          created_at: string
          grade: string
          id: string
          name: string
          school_level: string
          student_count: number
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          grade: string
          id?: string
          name: string
          school_level: string
          student_count?: number
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          grade?: string
          id?: string
          name?: string
          school_level?: string
          student_count?: number
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      exam_question_templates: {
        Row: {
          created_at: string
          default_count: number
          default_score_each: number
          id: string
          sort_order: number
          subject: string
          type_name: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          default_count?: number
          default_score_each?: number
          id?: string
          sort_order?: number
          subject: string
          type_name: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          default_count?: number
          default_score_each?: number
          id?: string
          sort_order?: number
          subject?: string
          type_name?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      exam_scores: {
        Row: {
          created_at: string
          exam_id: string
          id: string
          score: number | null
          student_id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          exam_id: string
          id?: string
          score?: number | null
          student_id: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          exam_id?: string
          id?: string
          score?: number | null
          student_id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "exam_scores_exam_id_fkey"
            columns: ["exam_id"]
            isOneToOne: false
            referencedRelation: "exams"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "exam_scores_student_id_fkey"
            columns: ["student_id"]
            isOneToOne: false
            referencedRelation: "students"
            referencedColumns: ["id"]
          },
        ]
      }
      exams: {
        Row: {
          class_id: string
          created_at: string
          exam_date: string
          id: string
          subject: string
          title: string
          total_score: number
          updated_at: string
          user_id: string
        }
        Insert: {
          class_id: string
          created_at?: string
          exam_date?: string
          id?: string
          subject: string
          title: string
          total_score?: number
          updated_at?: string
          user_id: string
        }
        Update: {
          class_id?: string
          created_at?: string
          exam_date?: string
          id?: string
          subject?: string
          title?: string
          total_score?: number
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "exams_class_id_fkey"
            columns: ["class_id"]
            isOneToOne: false
            referencedRelation: "classes"
            referencedColumns: ["id"]
          },
        ]
      }
      feature_flags: {
        Row: {
          enabled: boolean
          id: string
          key: string
          label: string
          scope: string
          scope_id: string | null
          updated_at: string
          updated_by: string | null
        }
        Insert: {
          enabled?: boolean
          id?: string
          key: string
          label?: string
          scope?: string
          scope_id?: string | null
          updated_at?: string
          updated_by?: string | null
        }
        Update: {
          enabled?: boolean
          id?: string
          key?: string
          label?: string
          scope?: string
          scope_id?: string | null
          updated_at?: string
          updated_by?: string | null
        }
        Relationships: []
      }
      knowledge_points: {
        Row: {
          code: string
          common_errors: string
          created_at: string
          difficulty: string
          embedding: string | null
          hours: number
          id: string
          is_weak: boolean
          key_point: string
          level: string
          mastery: number
          name: string
          postrequisite: string[]
          prerequisite: string[]
          related: string[]
          resources: Json
          unit_id: string
          updated_at: string
          user_id: string
        }
        Insert: {
          code: string
          common_errors?: string
          created_at?: string
          difficulty?: string
          embedding?: string | null
          hours?: number
          id?: string
          is_weak?: boolean
          key_point?: string
          level?: string
          mastery?: number
          name: string
          postrequisite?: string[]
          prerequisite?: string[]
          related?: string[]
          resources?: Json
          unit_id: string
          updated_at?: string
          user_id: string
        }
        Update: {
          code?: string
          common_errors?: string
          created_at?: string
          difficulty?: string
          embedding?: string | null
          hours?: number
          id?: string
          is_weak?: boolean
          key_point?: string
          level?: string
          mastery?: number
          name?: string
          postrequisite?: string[]
          prerequisite?: string[]
          related?: string[]
          resources?: Json
          unit_id?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "knowledge_points_unit_id_fkey"
            columns: ["unit_id"]
            isOneToOne: false
            referencedRelation: "subject_units"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          avatar_url: string | null
          created_at: string
          display_name: string | null
          id: string
          school_name: string | null
          updated_at: string
          user_id: string
        }
        Insert: {
          avatar_url?: string | null
          created_at?: string
          display_name?: string | null
          id?: string
          school_name?: string | null
          updated_at?: string
          user_id: string
        }
        Update: {
          avatar_url?: string | null
          created_at?: string
          display_name?: string | null
          id?: string
          school_name?: string | null
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      questions: {
        Row: {
          analysis: string | null
          answer: string | null
          content: string
          created_at: string
          difficulty: number
          embedding: string | null
          id: string
          knowledge_points: string[]
          score: number
          subject: string
          tags: string[]
          type: string
          updated_at: string
          use_count: number
          user_id: string
        }
        Insert: {
          analysis?: string | null
          answer?: string | null
          content: string
          created_at?: string
          difficulty?: number
          embedding?: string | null
          id?: string
          knowledge_points?: string[]
          score?: number
          subject: string
          tags?: string[]
          type?: string
          updated_at?: string
          use_count?: number
          user_id: string
        }
        Update: {
          analysis?: string | null
          answer?: string | null
          content?: string
          created_at?: string
          difficulty?: number
          embedding?: string | null
          id?: string
          knowledge_points?: string[]
          score?: number
          subject?: string
          tags?: string[]
          type?: string
          updated_at?: string
          use_count?: number
          user_id?: string
        }
        Relationships: []
      }
      students: {
        Row: {
          class_id: string
          created_at: string
          id: string
          name: string
          student_number: string
          updated_at: string
          user_id: string
        }
        Insert: {
          class_id: string
          created_at?: string
          id?: string
          name: string
          student_number: string
          updated_at?: string
          user_id: string
        }
        Update: {
          class_id?: string
          created_at?: string
          id?: string
          name?: string
          student_number?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "students_class_id_fkey"
            columns: ["class_id"]
            isOneToOne: false
            referencedRelation: "classes"
            referencedColumns: ["id"]
          },
        ]
      }
      subject_units: {
        Row: {
          created_at: string
          id: string
          name: string
          semester: string
          subject: string
          subtitle: string
          unit_index: number
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          name: string
          semester: string
          subject: string
          subtitle?: string
          unit_index: number
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          name?: string
          semester?: string
          subject?: string
          subtitle?: string
          unit_index?: number
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      system_config: {
        Row: {
          category: string
          description: string
          id: string
          key: string
          label: string
          updated_at: string
          updated_by: string | null
          value: Json
        }
        Insert: {
          category?: string
          description?: string
          id?: string
          key: string
          label?: string
          updated_at?: string
          updated_by?: string | null
          value?: Json
        }
        Update: {
          category?: string
          description?: string
          id?: string
          key?: string
          label?: string
          updated_at?: string
          updated_by?: string | null
          value?: Json
        }
        Relationships: []
      }
      teaching_resources: {
        Row: {
          created_at: string
          description: string | null
          detected_chapter: string | null
          detected_class: string | null
          detected_grade: string | null
          detected_school_level: string | null
          detected_subject: string | null
          detected_unit: string | null
          detection_confidence: number | null
          difficulty: number | null
          file_name: string
          file_size: number
          file_url: string
          id: string
          is_cross_class: boolean | null
          is_shared: boolean
          knowledge_point_count: number | null
          mime_type: string | null
          question_count: number | null
          rating: number
          source_label: string | null
          tags: string[] | null
          title: string
          type: string
          updated_at: string
          uploaded_from_class: string | null
          uploaded_from_grade: string | null
          user_id: string
          uses: number
        }
        Insert: {
          created_at?: string
          description?: string | null
          detected_chapter?: string | null
          detected_class?: string | null
          detected_grade?: string | null
          detected_school_level?: string | null
          detected_subject?: string | null
          detected_unit?: string | null
          detection_confidence?: number | null
          difficulty?: number | null
          file_name: string
          file_size?: number
          file_url: string
          id?: string
          is_cross_class?: boolean | null
          is_shared?: boolean
          knowledge_point_count?: number | null
          mime_type?: string | null
          question_count?: number | null
          rating?: number
          source_label?: string | null
          tags?: string[] | null
          title: string
          type?: string
          updated_at?: string
          uploaded_from_class?: string | null
          uploaded_from_grade?: string | null
          user_id: string
          uses?: number
        }
        Update: {
          created_at?: string
          description?: string | null
          detected_chapter?: string | null
          detected_class?: string | null
          detected_grade?: string | null
          detected_school_level?: string | null
          detected_subject?: string | null
          detected_unit?: string | null
          detection_confidence?: number | null
          difficulty?: number | null
          file_name?: string
          file_size?: number
          file_url?: string
          id?: string
          is_cross_class?: boolean | null
          is_shared?: boolean
          knowledge_point_count?: number | null
          mime_type?: string | null
          question_count?: number | null
          rating?: number
          source_label?: string | null
          tags?: string[] | null
          title?: string
          type?: string
          updated_at?: string
          uploaded_from_class?: string | null
          uploaded_from_grade?: string | null
          user_id?: string
          uses?: number
        }
        Relationships: []
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: Database["public"]["Enums"]["app_role"]
          school_id: string | null
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: Database["public"]["Enums"]["app_role"]
          school_id?: string | null
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: Database["public"]["Enums"]["app_role"]
          school_id?: string | null
          user_id?: string
        }
        Relationships: []
      }
      wrong_questions: {
        Row: {
          analysis: string | null
          class_id: string
          correct_answer: string | null
          created_at: string
          error_type: string
          exam_id: string | null
          id: string
          question_content: string
          student_answer: string | null
          student_id: string
          subject: string
          updated_at: string
          user_id: string
        }
        Insert: {
          analysis?: string | null
          class_id: string
          correct_answer?: string | null
          created_at?: string
          error_type?: string
          exam_id?: string | null
          id?: string
          question_content: string
          student_answer?: string | null
          student_id: string
          subject: string
          updated_at?: string
          user_id: string
        }
        Update: {
          analysis?: string | null
          class_id?: string
          correct_answer?: string | null
          created_at?: string
          error_type?: string
          exam_id?: string | null
          id?: string
          question_content?: string
          student_answer?: string | null
          student_id?: string
          subject?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "wrong_questions_class_id_fkey"
            columns: ["class_id"]
            isOneToOne: false
            referencedRelation: "classes"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "wrong_questions_exam_id_fkey"
            columns: ["exam_id"]
            isOneToOne: false
            referencedRelation: "exams"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "wrong_questions_student_id_fkey"
            columns: ["student_id"]
            isOneToOne: false
            referencedRelation: "students"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"]
          _user_id: string
        }
        Returns: boolean
      }
      is_any_admin: { Args: { _user_id: string }; Returns: boolean }
      match_knowledge_points: {
        Args: {
          filter_user_id?: string
          match_count?: number
          match_threshold?: number
          query_embedding: string
        }
        Returns: {
          code: string
          common_errors: string
          difficulty: string
          id: string
          is_weak: boolean
          level: string
          mastery: number
          name: string
          similarity: number
        }[]
      }
      match_questions: {
        Args: {
          filter_user_id?: string
          match_count?: number
          match_threshold?: number
          query_embedding: string
        }
        Returns: {
          content: string
          difficulty: number
          id: string
          knowledge_points: string[]
          score: number
          similarity: number
          subject: string
          tags: string[]
          type: string
          use_count: number
        }[]
      }
    }
    Enums: {
      app_role: "super_admin" | "school_admin"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      app_role: ["super_admin", "school_admin"],
    },
  },
} as const
