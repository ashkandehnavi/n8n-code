namespace app_mt7li7mg_ezi7av.Models;

public sealed class TaskItem
{
    public int Id { get; }
    public string Title { get; }
    public string Description { get; }
    public bool IsCompleted { get; private set; }
    public DateTime CreatedAt { get; }

    public TaskItem(int id, string title, string description)
    {
        Id = id;
        Title = title;
        Description = description;
        CreatedAt = DateTime.Now;
    }

    public void MarkCompleted()
    {
        IsCompleted = true;
    }
}
