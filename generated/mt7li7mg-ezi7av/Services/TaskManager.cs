using app_mt7li7mg_ezi7av.Models;

namespace app_mt7li7mg_ezi7av.Services;

public sealed class TaskManager
{
    private readonly List<TaskItem> _tasks = new();
    private int _nextId = 1;

    public TaskItem Add(string title, string description)
    {
        var task = new TaskItem(_nextId++, title, description);
        _tasks.Add(task);
        return task;
    }

    public IReadOnlyList<TaskItem> GetAll()
    {
        return _tasks.AsReadOnly();
    }

    public IReadOnlyList<TaskItem> GetOpenTasks()
    {
        return _tasks.Where(task => !task.IsCompleted).ToList();
    }

    public TaskItem? FindById(int id)
    {
        return _tasks.FirstOrDefault(task => task.Id == id);
    }

    public bool Complete(int id)
    {
        var task = FindById(id);
        if (task is null || task.IsCompleted)
        {
            return false;
        }

        task.MarkCompleted();
        return true;
    }

    public bool Delete(int id)
    {
        var task = FindById(id);
        return task is not null && _tasks.Remove(task);
    }
}
